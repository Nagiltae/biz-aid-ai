package com.bizaid.ai.presentation;

import com.bizaid.ai.application.AiDtos;
import com.bizaid.ai.application.RecommendationWorkflowService;
import com.bizaid.auth.domain.AuthUser;
import com.bizaid.usage.application.AiUsageService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Size;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

/**
 * V2-3 추천 흐름 API. 클라이언트는 응답의 nextAction만 보고 continue(다음 단계) 또는 answers(부족 정보)를 요청한다.
 * 어떤 공고를 판정할지 같은 업무 결정은 클라이언트가 하지 않는다. 한 요청은 판정 LLM 최대 1건이라 Spring 제한시간 안에 끝난다.
 */
@RestController
@RequestMapping("/api/ai/workflows")
public class WorkflowController {

    private final RecommendationWorkflowService workflowService;
    private final AiUsageService usage;

    public WorkflowController(RecommendationWorkflowService workflowService, AiUsageService usage) {
        this.workflowService = workflowService;
        this.usage = usage;
    }

    public record AnswersRequest(
            @NotEmpty(message = "답변할 정보를 입력해 주세요.") @Size(max = 20, message = "한 번에 20개까지 답할 수 있습니다.")
            Map<String, Object> answers) {
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public AiDtos.WorkflowResponse start(@AuthenticationPrincipal AuthUser user,
                                         @Valid @RequestBody AiRequests.PersonalizedSearchRequest request) {
        // 하루 사용 횟수는 추천 시작에서만 1 쓴다. 다음 단계 진행·부족 정보 답변은 같은 추천의 일부라 세지 않는다.
        return usage.run(user, () -> workflowService.start(user.id(), request.query()));
    }

    @GetMapping
    public java.util.List<AiDtos.WorkflowSummary> list(@AuthenticationPrincipal AuthUser user) {
        return workflowService.list(user.id());
    }

    @GetMapping("/{workflowId}")
    public AiDtos.WorkflowResponse get(@AuthenticationPrincipal AuthUser user, @PathVariable Long workflowId) {
        return workflowService.get(user.id(), workflowId);
    }

    @PostMapping("/{workflowId}/continue")
    public AiDtos.WorkflowResponse advance(@AuthenticationPrincipal AuthUser user, @PathVariable Long workflowId) {
        return workflowService.advance(user.id(), workflowId);
    }

    @PostMapping("/{workflowId}/answers")
    public AiDtos.WorkflowResponse answer(@AuthenticationPrincipal AuthUser user, @PathVariable Long workflowId,
                                          @Valid @RequestBody AnswersRequest request) {
        return workflowService.answer(user.id(), workflowId, request.answers());
    }
}
