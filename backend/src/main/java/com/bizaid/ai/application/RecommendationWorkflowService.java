package com.bizaid.ai.application;

import com.bizaid.activity.application.ActivityLogService;
import com.bizaid.activity.domain.ActivityAction;
import com.bizaid.ai.domain.AiWorkflow;
import com.bizaid.ai.infrastructure.AiWorkflowRepository;
import com.bizaid.common.error.ApiException;
import com.bizaid.common.error.ErrorCode;
import com.bizaid.company.application.CompanyService;
import com.bizaid.company.domain.Company;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import java.time.Clock;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

/**
 * V2-3 상태 기반 추천 흐름의 Spring 쪽 유스케이스: workflow 시작·조회·다음 단계 진행·부족 정보 답변.
 *
 * <p>역할 분리: 흐름의 분기·판정은 FastAPI(LangGraph)가 받은 State로 한 단계씩 실행한다. Spring은 인증·기업정보 조회,
 * State의 MySQL(ai_workflows) 저장·복원, 소유권 확인, 동시 진행 방지만 한다. 다음에 무엇을 할지는 State가 정하므로
 * 클라이언트는 "다음 단계 진행"만 요청한다.
 *
 * <p>동시 진행 방지: ① 짧은 트랜잭션에서 단계 점유(step_started_at) + 낙관적 잠금(version) 저장 → 같은 버전을 읽은 다른 요청은 실패
 * ② 트랜잭션 밖에서 FastAPI 호출(최대 판정 1건, DB 연결을 잡지 않음) ③ 점유한 버전 그대로일 때만 새 State 저장.
 * 그래서 같은 workflow를 두 번 진행해 같은 공고를 중복 판정·저장하지 않는다.
 */
@Service
public class RecommendationWorkflowService {

    private static final int MAX_ANSWERS = 20;

    private final AiWorkflowRepository workflows;
    private final CompanyService companyService;
    private final AiGateway aiGateway;
    private final ActivityLogService activityLog;
    private final Clock clock;
    private final ObjectMapper snakeCase;
    private final TransactionTemplate transaction;

    public RecommendationWorkflowService(AiWorkflowRepository workflows, CompanyService companyService, AiGateway aiGateway,
                                         ActivityLogService activityLog, Clock clock, ObjectMapper objectMapper,
                                         PlatformTransactionManager transactionManager) {
        this.workflows = workflows;
        this.companyService = companyService;
        this.aiGateway = aiGateway;
        this.activityLog = activityLog;
        this.clock = clock;
        // State JSON은 FastAPI 이름 규칙(snake_case) 그대로 저장하고, 응답 DTO로 읽을 때만 이름을 바꾼다.
        this.snakeCase = objectMapper.copy().setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
                .configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false);
        this.transaction = new TransactionTemplate(transactionManager);
    }

    /** 시작: 개인화 검색 + Top 3 확정까지만(판정 LLM 없음). 기업정보는 V1 단일 판정과 같은 snapshot(저장된 값만)이다. */
    public AiDtos.WorkflowResponse start(Long userId, String query) {
        Company company = companyService.find(userId);
        AiDtos.CompanyProfileSnapshot snapshot = EligibilityService.snapshot(company, null);
        JsonNode state = aiGateway.startWorkflow(new AiDtos.PersonalizedEligibilityCommand(query.strip(), snapshot));
        AiDtos.WorkflowState view = view(state);
        AiWorkflow saved = transaction.execute(status -> workflows.save(
                new AiWorkflow(userId, write(state), view.status(), view.currentStep(), clock.instant())));
        activityLog.success(ActivityAction.AI_QUERY, userId, "WORKFLOW", saved.getId(),
                Map.of("mode", "WORKFLOW_START", "status", view.status()));
        return response(saved.getId(), view);
    }

    public AiDtos.WorkflowResponse get(Long userId, Long workflowId) {
        AiWorkflow workflow = transaction.execute(status -> owned(userId, workflowId));
        return response(workflowId, view(read(workflow.getStateJson())));
    }

    /** 다음 단계 1개 진행. 무엇을 할지(다음 공고 판정, 부족 정보 통합)는 State가 정한다. */
    public AiDtos.WorkflowResponse advance(Long userId, Long workflowId) {
        return step(userId, workflowId, "continue", Map.of(), "IN_PROGRESS");
    }

    /** 부족 정보 답변 제출. 지금 묻고 있는 field ID만 받고, 값은 이 흐름의 임시 정보로만 저장한다(companies는 바꾸지 않음). */
    public AiDtos.WorkflowResponse answer(Long userId, Long workflowId, Map<String, Object> answers) {
        return step(userId, workflowId, "answer", answers, "WAITING_FOR_USER");
    }

    private AiDtos.WorkflowResponse step(Long userId, Long workflowId, String command, Map<String, Object> answers,
                                         String requiredStatus) {
        Claim claim = claim(userId, workflowId, command, answers, requiredStatus);
        JsonNode next;
        try {
            next = aiGateway.advanceWorkflow(claim.state(), command, answers);
        } catch (ApiException exception) {
            // AI 단계가 실패하면 점유만 풀고 State는 그대로 둔다(같은 단계를 사용자가 다시 요청할 수 있다).
            transaction.executeWithoutResult(status -> {
                AiWorkflow workflow = owned(userId, workflowId);
                if (workflow.getVersion().equals(claim.version())) {
                    workflow.releaseStep(clock.instant());
                    workflows.saveAndFlush(workflow);
                }
            });
            activityLog.failure(ActivityAction.ELIGIBILITY_CHECK, userId, "WORKFLOW", workflowId, exception.errorCode().code(),
                    Map.of("mode", "WORKFLOW_STEP", "command", command));
            throw exception;
        }
        AiDtos.WorkflowState view = view(next);
        transaction.executeWithoutResult(status -> {
            AiWorkflow workflow = owned(userId, workflowId);
            // BOUNDARY: 점유한 뒤 다른 요청이 흐름을 바꿨다면(오래된 점유를 다시 가져간 경우) 이 결과를 덮어쓰지 않는다.
            if (!workflow.getVersion().equals(claim.version())) {
                throw new ApiException(ErrorCode.WORKFLOW_BUSY);
            }
            workflow.applyState(write(next), view.status(), view.currentStep(), clock.instant());
            workflows.saveAndFlush(workflow);
        });
        activityLog.success(ActivityAction.ELIGIBILITY_CHECK, userId, "WORKFLOW", workflowId,
                Map.of("mode", "WORKFLOW_STEP", "command", command, "status", view.status()));
        return response(workflowId, view);
    }

    private record Claim(JsonNode state, Long version) {
    }

    private Claim claim(Long userId, Long workflowId, String command, Map<String, Object> answers, String requiredStatus) {
        try {
            return transaction.execute(status -> {
                AiWorkflow workflow = owned(userId, workflowId);
                if (!requiredStatus.equals(workflow.getStatus())) {
                    throw new ApiException(ErrorCode.WORKFLOW_INVALID_STATE);
                }
                if (workflow.isBusy(clock.instant())) {
                    throw new ApiException(ErrorCode.WORKFLOW_BUSY);
                }
                JsonNode state = read(workflow.getStateJson());
                if ("answer".equals(command)) {
                    checkAnswers(view(state), answers);
                }
                workflow.claimStep(clock.instant());
                workflows.saveAndFlush(workflow);
                return new Claim(state, workflow.getVersion());
            });
        } catch (OptimisticLockingFailureException exception) {
            // 같은 버전을 읽은 다른 요청이 먼저 점유했다.
            throw new ApiException(ErrorCode.WORKFLOW_BUSY);
        }
    }

    /** 지금 State가 묻는 field ID만, 최대 20개까지 받는다. 값 형식은 FastAPI가 기존 Snapshot 규칙으로 다시 검사한다. */
    private void checkAnswers(AiDtos.WorkflowState view, Map<String, Object> answers) {
        Set<String> asked = view.missingInformation() == null ? Set.of()
                : view.missingInformation().stream().map(AiDtos.MissingField::fieldId).collect(Collectors.toSet());
        if (answers == null || answers.isEmpty() || answers.size() > MAX_ANSWERS || !asked.containsAll(answers.keySet())
                || answers.values().stream().anyMatch(value -> value == null)) {
            throw new ApiException(ErrorCode.VALIDATION_FAILED);
        }
    }

    private AiWorkflow owned(Long userId, Long workflowId) {
        // 다른 사용자의 흐름은 존재 여부도 알려 주지 않는다.
        return workflows.findById(workflowId).filter(workflow -> workflow.isOwnedBy(userId))
                .orElseThrow(() -> new ApiException(ErrorCode.WORKFLOW_NOT_FOUND));
    }

    private AiDtos.WorkflowState view(JsonNode state) {
        try {
            return snakeCase.treeToValue(state, AiDtos.WorkflowState.class);
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException(exception);
        }
    }

    private JsonNode read(String json) {
        try {
            return snakeCase.readTree(json);
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException(exception);
        }
    }

    private String write(JsonNode state) {
        try {
            return snakeCase.writeValueAsString(state);
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException(exception);
        }
    }

    private static AiDtos.WorkflowResponse response(Long workflowId, AiDtos.WorkflowState view) {
        List<AiDtos.WorkflowEvaluation> evaluations = view.evaluations() == null ? List.of() : view.evaluations();
        int completed = (int) evaluations.stream().filter(item -> "COMPLETED".equals(item.evaluationStatus())).count();
        int failed = (int) evaluations.stream().filter(item -> "FAILED".equals(item.evaluationStatus())).count();
        int pending = view.pending() == null ? 0 : view.pending().size();
        AiDtos.WorkflowProgress progress = new AiDtos.WorkflowProgress(evaluations.size(), completed, failed, pending,
                view.round() == null ? 0 : view.round());
        return new AiDtos.WorkflowResponse(workflowId, view.status(), view.currentStep(), view.nextAction(), progress, view.search(),
                evaluations, view.missingInformation() == null ? List.of() : view.missingInformation(),
                view.temporaryCompanyFacts() == null ? Map.of() : view.temporaryCompanyFacts(), view.failureCode(),
                view.finalResult());
    }
}
