package com.bizaid.ai.infrastructure;

import com.bizaid.ai.application.AiDtos;
import com.bizaid.ai.application.AiGateway;
import com.bizaid.common.error.ApiException;
import com.bizaid.common.error.ErrorCode;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import java.io.IOException;
import java.io.InputStream;
import java.net.ConnectException;
import java.net.http.HttpClient;
import java.net.http.HttpConnectTimeoutException;
import java.net.http.HttpTimeoutException;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.stream.Stream;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.MediaType;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;

/**
 * FastAPI 내부 AI API를 HTTP로 호출하는 AI 연결 창구(AiGateway) 구현.
 *
 * <p>WHY 동기 RestClient: 서비스가 Spring MVC(요청당 스레드)라 WebFlux를 새로 들이지 않고 Spring 6 기본 동기 client로 충분하다.
 * <p>BOUNDARY: 요청을 보내고 응답이 계약대로인지 검증만 한다. 답변·목록 순위·자격 상태·근거를 다시 계산하거나 고치지 않는다.
 * 계약을 어긴 응답은 고쳐 쓰지 않고 ai_response_invalid로 거부한다.
 * <p>자동 재시도(retry) 없음: 같은 LLM 요청이 중복 실행되고 대기 시간이 길어지며 메시지가 이중 저장될 수 있다. 사용자가 직접 다시 시도한다.
 */
@Component
public class HttpAiGateway implements AiGateway {

    static final String KEY_HEADER = "X-Internal-Api-Key";
    private static final Logger log = LoggerFactory.getLogger(HttpAiGateway.class);
    private static final Set<String> REQUEST_MODES = Set.of("SEARCH_LIST", "DOCUMENT_QA");
    private static final Set<String> PERSONALIZED_STATUSES =
            Set.of("LISTED", "NO_CANDIDATES", "NO_INDEXED_PROGRAMS", "COMPANY_CLOSED", "CONDITION_CONFLICT");
    private static final int PERSONALIZED_TOP_K = 3;
    /** 흐름 상태별로 허용되는 다음 행동. 둘이 어긋난 State는 저장하지 않는다. */
    private static final Map<String, String> WORKFLOW_NEXT =
            Map.of("IN_PROGRESS", "CONTINUE", "WAITING_FOR_USER", "ANSWER", "COMPLETED", "NONE", "FAILED", "NONE");
    private static final Set<String> ELIGIBILITY_STATUSES = Set.of("ELIGIBLE", "INELIGIBLE", "NEEDS_MORE_INFO", "INSUFFICIENT_EVIDENCE");

    private final RestClient client;
    private final ObjectMapper snakeCase;
    private final String apiKey;

    public HttpAiGateway(AiProperties properties, ObjectMapper objectMapper) {
        // 연결 제한시간은 짧게(서버가 꺼져 있으면 빨리 알림), 응답 제한시간은 길게(LLM 생성 시간) 따로 둔다.
        HttpClient httpClient = HttpClient.newBuilder().connectTimeout(properties.connectTimeout())
                .version(HttpClient.Version.HTTP_1_1).build();
        JdkClientHttpRequestFactory factory = new JdkClientHttpRequestFactory(httpClient);
        factory.setReadTimeout(properties.responseTimeout());
        this.client = RestClient.builder().baseUrl(properties.baseUrl()).requestFactory(factory).build();
        // FastAPI JSON(snake_case) ↔ Java(camelCase) 이름 규칙만 바꾼다. 모르는 field는 무시해 FastAPI가 field를 추가해도 깨지지 않는다.
        this.snakeCase = objectMapper.copy().setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
                .configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false);
        this.apiKey = properties.apiKey() == null ? "" : properties.apiKey();
    }

    @Override
    public AiDtos.AiQueryResult query(String query) {
        AiDtos.AiQueryResult result = post("/internal/v1/query", new QueryPayload(query), AiDtos.AiQueryResult.class);
        if (result == null || !REQUEST_MODES.contains(result.requestMode()) || result.status() == null) {
            throw invalid("query: unknown request_mode or missing status");
        }
        if (result.programs() != null) {
            Set<String> seen = new HashSet<>();
            // 목록은 공고 단위다. 중복이 오면 Spring이 지우지 않고(순위 변경이 되므로) 계약 위반으로 거부한다.
            if (!result.programs().stream().allMatch(program -> program.pblancId() != null && seen.add(program.pblancId()))) {
                throw invalid("query: duplicate or missing pblanc_id in programs");
            }
        }
        return result;
    }

    @Override
    public AiDtos.EligibilityResult evaluateEligibility(AiDtos.EligibilityCommand command) {
        AiDtos.EligibilityResult result = post("/internal/v1/eligibility",
                new EligibilityPayload(command.pblancId(), command.companyProfile()), AiDtos.EligibilityResult.class);
        checkEligibility(command.pblancId(), result);
        return result;
    }

    /** 단일 판정과 Top 3 판정이 같은 계약 검증을 쓴다. */
    private void checkEligibility(String pblancId, AiDtos.EligibilityResult result) {
        if (result == null || !ELIGIBILITY_STATUSES.contains(result.status()) || !pblancId.equals(result.pblancId())) {
            throw invalid("eligibility: unknown status or different pblanc_id");
        }
        // BOUNDARY: 판정 근거는 요청한 공고의 공고문에서만 와야 한다. 다른 공고 근거가 섞이면 결과를 쓰지 않는다.
        boolean scoped = result.criteria() == null || result.criteria().stream()
                .flatMap(criterion -> criterion.citations() == null ? Stream.empty() : criterion.citations().stream())
                .allMatch(citation -> pblancId.equals(citation.pblancId()));
        if (!scoped) {
            throw invalid("eligibility: citation outside the target program");
        }
    }

    @Override
    public AiDtos.PersonalizedSearchResult personalizedSearch(AiDtos.PersonalizedSearchCommand command) {
        AiDtos.PersonalizedSearchResult result = post("/internal/v2/personalized-search", command,
                AiDtos.PersonalizedSearchResult.class);
        checkPersonalizedSearch(result);
        return result;
    }

    private void checkPersonalizedSearch(AiDtos.PersonalizedSearchResult result) {
        if (result == null || !PERSONALIZED_STATUSES.contains(result.status()) || result.programs() == null) {
            throw invalid("personalized: unknown status or missing programs");
        }
        Set<String> seen = new HashSet<>();
        // Top 3·공고 중복 없음이 계약이다. 어기면 Spring이 잘라내거나 다시 정렬하지 않고 거부한다.
        if (result.programs().size() > PERSONALIZED_TOP_K
                || !result.programs().stream().allMatch(program -> program.pblancId() != null && seen.add(program.pblancId()))) {
            throw invalid("personalized: more than top 3 or duplicate programs");
        }
    }

    @Override
    public AiDtos.PersonalizedEligibilityResult personalizedEligibility(AiDtos.PersonalizedEligibilityCommand command) {
        AiDtos.PersonalizedEligibilityResult result = post("/internal/v2/personalized-eligibility", command,
                AiDtos.PersonalizedEligibilityResult.class);
        if (result == null || result.evaluations() == null) {
            throw invalid("personalized eligibility: missing search or evaluations");
        }
        checkPersonalizedSearch(result.search());
        List<AiDtos.ProgramItem> programs = result.search().programs();
        // 판정 목록은 검색 Top 3와 같은 순서·같은 공고여야 한다(순위를 다시 매기거나 빠뜨리지 않음).
        if (result.evaluations().size() != programs.size()) {
            throw invalid("personalized eligibility: evaluations differ from top programs");
        }
        for (int index = 0; index < programs.size(); index++) {
            AiDtos.ProgramEvaluation evaluation = result.evaluations().get(index);
            String pblancId = programs.get(index).pblancId();
            if (!pblancId.equals(evaluation.pblancId())) {
                throw invalid("personalized eligibility: evaluation order differs from search order");
            }
            // 공고별 결과는 완료(판정 있음) 또는 실패(오류 코드 있음, 판정 없음) 둘 중 하나다. 실패를 결과로 바꾸지 않는다.
            if ("COMPLETED".equals(evaluation.evaluationStatus())) {
                checkEligibility(pblancId, evaluation.eligibility());
            } else if (!"FAILED".equals(evaluation.evaluationStatus()) || evaluation.errorCode() == null
                    || evaluation.eligibility() != null) {
                throw invalid("personalized eligibility: invalid per-program status");
            }
        }
        return result;
    }

    @Override
    public JsonNode startWorkflow(AiDtos.PersonalizedEligibilityCommand command) {
        return checkWorkflow(post("/internal/v2/workflows/start", command, JsonNode.class));
    }

    @Override
    public JsonNode advanceWorkflow(JsonNode state, String command, Map<String, Object> answers) {
        return checkWorkflow(post("/internal/v2/workflows/advance", new WorkflowAdvancePayload(state, command, answers),
                JsonNode.class));
    }

    /**
     * 돌려받은 State가 흐름 계약을 지키는지 확인하고 State JSON을 그대로 돌려준다(Spring은 State를 고치지 않는다).
     * 상태와 다음 행동의 짝, 판정 목록이 Top 3 순서와 같은지, 완료된 판정의 근거가 그 공고뿐인지 본다.
     */
    private JsonNode checkWorkflow(JsonNode body) {
        JsonNode state = body == null ? null : body.get("state");
        AiDtos.WorkflowState view;
        try {
            view = state == null || !state.isObject() ? null : snakeCase.treeToValue(state, AiDtos.WorkflowState.class);
        } catch (IOException exception) {
            view = null;
        }
        if (view == null || !Objects.equals(WORKFLOW_NEXT.get(view.status()), view.nextAction()) || view.currentStep() == null) {
            throw invalid("workflow: unknown status or inconsistent next action");
        }
        List<AiDtos.WorkflowEvaluation> evaluations = view.evaluations() == null ? List.of() : view.evaluations();
        List<AiDtos.ProgramItem> programs = view.search() == null || view.search().programs() == null
                ? List.of() : view.search().programs();
        if (evaluations.size() != programs.size() || programs.size() > PERSONALIZED_TOP_K) {
            throw invalid("workflow: evaluations differ from top programs");
        }
        for (int index = 0; index < programs.size(); index++) {
            AiDtos.WorkflowEvaluation evaluation = evaluations.get(index);
            if (!programs.get(index).pblancId().equals(evaluation.pblancId())) {
                throw invalid("workflow: evaluation order differs from search order");
            }
            if ("COMPLETED".equals(evaluation.evaluationStatus())) {
                checkEligibility(evaluation.pblancId(), evaluation.eligibility());
            } else if (!Set.of("PENDING", "FAILED").contains(evaluation.evaluationStatus())
                    || ("FAILED".equals(evaluation.evaluationStatus()) && evaluation.errorCode() == null)) {
                throw invalid("workflow: invalid per-program status");
            }
        }
        checkFinalResult(view, evaluations);
        return state;
    }

    /** 최종 결과 묶음별로 허용하는 기존 판정 상태. 판정 실패(null)는 판단 불가에만 들어간다. */
    private static final Map<String, Set<String>> FINAL_STATUSES = Map.of("recommended", Set.of("ELIGIBLE"),
            "excluded", Set.of("INELIGIBLE"), "unresolved", Set.of("INSUFFICIENT_EVIDENCE", "NEEDS_MORE_INFO"));

    /**
     * 최종 결과는 COMPLETED에만 있고, 판정한 공고를 빠짐없이 한 번씩 담으며, 묶음 안 순서는 검색 순위 그대로여야 한다.
     * 근거는 그 공고 것만, 이유가 가리키는 근거는 항목 citations 안에 있어야 한다.
     */
    private void checkFinalResult(AiDtos.WorkflowState view, List<AiDtos.WorkflowEvaluation> evaluations) {
        AiDtos.FinalResult result = view.finalResult();
        if (!"COMPLETED".equals(view.status())) {
            if (result != null) {
                throw invalid("workflow: final result before completion");
            }
            return;
        }
        if (result == null || result.counts() == null) {
            throw invalid("workflow: completed without final result");
        }
        Map<String, List<AiDtos.FinalItem>> groups = Map.of("recommended", nullSafe(result.recommended()),
                "excluded", nullSafe(result.excluded()), "unresolved", nullSafe(result.unresolved()));
        Set<String> seen = new HashSet<>();
        for (Map.Entry<String, List<AiDtos.FinalItem>> group : groups.entrySet()) {
            int previousRank = 0;
            for (AiDtos.FinalItem item : group.getValue()) {
                boolean statusFits = item.eligibilityStatus() == null
                        ? "unresolved".equals(group.getKey()) && item.errorCode() != null
                        : FINAL_STATUSES.get(group.getKey()).contains(item.eligibilityStatus());
                if (!statusFits || item.rank() == null || item.rank() <= previousRank || !seen.add(item.pblancId())) {
                    throw invalid("workflow: final result category, rank order or duplicate");
                }
                previousRank = item.rank();
                Set<String> evidence = new HashSet<>();
                for (AiDtos.Citation citation : nullSafe(item.citations())) {
                    // BOUNDARY: 최종 결과도 공고별 근거 격리를 그대로 지킨다.
                    if (!item.pblancId().equals(citation.pblancId())) {
                        throw invalid("workflow: final result citation outside the program");
                    }
                    evidence.add(citation.evidenceId());
                }
                boolean referenced = nullSafe(item.reasons()).stream()
                        .allMatch(reason -> evidence.containsAll(nullSafe(reason.evidenceIds())));
                if (!referenced) {
                    throw invalid("workflow: final reason cites unknown evidence");
                }
            }
        }
        Set<String> evaluated = new HashSet<>();
        evaluations.forEach(evaluation -> evaluated.add(evaluation.pblancId()));
        AiDtos.FinalCounts counts = result.counts();
        if (!seen.equals(evaluated) || !Objects.equals(counts.recommended(), groups.get("recommended").size())
                || !Objects.equals(counts.excluded(), groups.get("excluded").size())
                || !Objects.equals(counts.unresolved(), groups.get("unresolved").size())) {
            throw invalid("workflow: final result does not cover evaluated programs");
        }
    }

    private static <T> List<T> nullSafe(List<T> values) {
        return values == null ? List.of() : values;
    }

    /** FastAPI 요청 본문(/internal/v1/query, /internal/v1/eligibility). HTTP 전송 형식이라 이 구현 안에만 둔다. */
    private record QueryPayload(String query) {
    }

    private record EligibilityPayload(String pblancId, AiDtos.CompanyProfileSnapshot companyProfile) {
    }

    private record WorkflowAdvancePayload(JsonNode state, String command, Map<String, Object> answers) {
    }

    private <T> T post(String path, Object body, Class<T> type) {
        byte[] payload;
        try {
            payload = snakeCase.writeValueAsBytes(body);
        } catch (IOException exception) {
            throw new IllegalStateException(exception);
        }
        try {
            return client.post().uri(path).contentType(MediaType.APPLICATION_JSON).accept(MediaType.APPLICATION_JSON)
                    .header(KEY_HEADER, apiKey).body(payload)
                    .exchange((request, response) -> {
                        int status = response.getStatusCode().value();
                        if (status >= 200 && status < 300) {
                            return read(response.getBody(), type);
                        }
                        throw mapError(path, status, errorCode(response.getBody()));
                    });
        } catch (ResourceAccessException exception) {
            throw mapIo(path, exception);
        }
    }

    private <T> T read(InputStream body, Class<T> type) {
        try {
            return snakeCase.readValue(body, type);
        } catch (IOException exception) {
            throw invalid("response is not the contracted JSON");
        }
    }

    private String errorCode(InputStream body) {
        try {
            JsonNode node = snakeCase.readTree(body);
            return node == null ? null : node.path("error").path("code").asText(null);
        } catch (IOException exception) {
            return null;
        }
    }

    /**
     * FastAPI HTTP 오류를 서비스 공통 오류로 바꾼다. FastAPI 오류 code는 로그에만 남기고 React에는 내부 사정(Ollama·Qdrant·DB 상세)을 보내지 않는다.
     * 401/403은 최종 사용자의 로그인 문제가 아니라 Spring↔FastAPI 공유 키 설정 문제라 502 ai_service_auth_failed로 바꾼다.
     */
    ApiException mapError(String path, int status, String upstreamCode) {
        log.warn("AI upstream error path={} status={} code={}", path, status, upstreamCode);
        ErrorCode code = switch (status) {
            case 401, 403 -> ErrorCode.AI_SERVICE_AUTH_FAILED;
            case 404 -> Objects.equals(upstreamCode, "eligibility_program_not_found_or_inactive")
                    ? ErrorCode.PROGRAM_NOT_FOUND : ErrorCode.AI_SERVICE_ERROR;
            // 사용자 입력(추가 정보 답변·일시 정보)의 형식·field 오류는 사용자에게 고칠 수 있는 400으로 알린다.
            case 422 -> upstreamCode != null && (upstreamCode.startsWith("company_profile_invalid")
                    || upstreamCode.startsWith("workflow_answer")) ? ErrorCode.VALIDATION_FAILED : ErrorCode.AI_SERVICE_ERROR;
            // 흐름 상태와 맞지 않는 진행 요청(이미 완료 등)
            case 409 -> ErrorCode.WORKFLOW_INVALID_STATE;
            case 502 -> ErrorCode.AI_RESPONSE_INVALID;
            case 503 -> Objects.equals(upstreamCode, "internal_auth_not_configured")
                    ? ErrorCode.AI_SERVICE_AUTH_FAILED : ErrorCode.AI_SERVICE_UNAVAILABLE;
            default -> ErrorCode.AI_SERVICE_ERROR;
        };
        return new ApiException(code);
    }

    private ApiException mapIo(String path, ResourceAccessException exception) {
        Throwable cause = exception.getCause();
        // HttpConnectTimeoutException은 HttpTimeoutException의 하위 타입이다. 연결 실패(서버 없음)를 응답 지연보다 먼저 가른다.
        boolean connect = cause instanceof ConnectException || cause instanceof HttpConnectTimeoutException;
        boolean timeout = !connect && cause instanceof HttpTimeoutException;
        log.warn("AI upstream io failure path={} type={}", path, cause == null ? "unknown" : cause.getClass().getSimpleName());
        return new ApiException(timeout ? ErrorCode.AI_SERVICE_TIMEOUT : ErrorCode.AI_SERVICE_UNAVAILABLE);
    }

    private ApiException invalid(String reason) {
        log.warn("AI response rejected: {}", reason);
        return new ApiException(ErrorCode.AI_RESPONSE_INVALID);
    }
}
