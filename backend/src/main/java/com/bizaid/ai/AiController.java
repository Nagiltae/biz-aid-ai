package com.bizaid.ai;

import com.bizaid.auth.AuthUser;
import jakarta.validation.Valid;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

/**
 * React가 호출하는 AI 기능 입구. React는 FastAPI를 직접 부르지 않고 항상 이 API를 거친다.
 * 판단 결과(NO_CANDIDATES·INSUFFICIENT_EVIDENCE·NEEDS_MORE_INFO·INELIGIBLE 등)는 정상 응답(200)이고, AI 호출 실패만 5xx 오류다.
 */
@RestController
public class AiController {

    private final AiQueryService aiQueryService;
    private final EligibilityService eligibilityService;

    public AiController(AiQueryService aiQueryService, EligibilityService eligibilityService) {
        this.aiQueryService = aiQueryService;
        this.eligibilityService = eligibilityService;
    }

    @PostMapping("/api/ai/query")
    public AiDtos.AiQueryResponse query(@AuthenticationPrincipal AuthUser user, @Valid @RequestBody AiDtos.AiQueryRequest request) {
        return aiQueryService.query(user.id(), request);
    }

    @PostMapping("/api/programs/{pblancId}/eligibility")
    public AiDtos.EligibilityResult eligibility(@AuthenticationPrincipal AuthUser user, @PathVariable String pblancId,
                                                @Valid @RequestBody(required = false) AiDtos.EligibilityRequest request) {
        return eligibilityService.evaluate(user.id(), pblancId, request);
    }
}
