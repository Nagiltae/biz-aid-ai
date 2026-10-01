package com.bizaid.ai.presentation;

import com.bizaid.ai.application.AiDtos;
import com.bizaid.ai.application.AiQueryService;
import com.bizaid.ai.application.EligibilityService;
import com.bizaid.ai.application.PersonalizedEligibilityService;
import com.bizaid.ai.application.PersonalizedSearchService;
import com.bizaid.auth.domain.AuthUser;
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
    private final PersonalizedSearchService personalizedSearchService;
    private final PersonalizedEligibilityService personalizedEligibilityService;

    public AiController(AiQueryService aiQueryService, EligibilityService eligibilityService,
                        PersonalizedSearchService personalizedSearchService,
                        PersonalizedEligibilityService personalizedEligibilityService) {
        this.aiQueryService = aiQueryService;
        this.eligibilityService = eligibilityService;
        this.personalizedSearchService = personalizedSearchService;
        this.personalizedEligibilityService = personalizedEligibilityService;
    }

    /** V2 개인화 검색 Top 3 + 공고별 자격 판정. 조합은 서버(FastAPI)가 하고 공고별 실패는 그 공고에만 표시된다. */
    @PostMapping("/api/ai/personalized-eligibility")
    public AiDtos.PersonalizedEligibilityResult personalizedEligibility(
            @AuthenticationPrincipal AuthUser user, @Valid @RequestBody AiRequests.PersonalizedSearchRequest request) {
        return personalizedEligibilityService.evaluate(user.id(), request.query());
    }

    /** V2 기업정보 기반 개인화 검색(Top 3). V1 /api/ai/query 동작은 그대로다. */
    @PostMapping("/api/ai/personalized-search")
    public AiDtos.PersonalizedSearchResult personalizedSearch(@AuthenticationPrincipal AuthUser user,
                                                              @Valid @RequestBody AiRequests.PersonalizedSearchRequest request) {
        return personalizedSearchService.search(user.id(), request.query());
    }

    @PostMapping("/api/ai/query")
    public AiDtos.AiQueryResponse query(@AuthenticationPrincipal AuthUser user,
                                       @Valid @RequestBody AiRequests.AiQueryRequest request) {
        return aiQueryService.query(user.id(), request.query(), request.conversationId());
    }

    @PostMapping("/api/programs/{pblancId}/eligibility")
    public AiDtos.EligibilityResult eligibility(@AuthenticationPrincipal AuthUser user, @PathVariable String pblancId,
                                                @Valid @RequestBody(required = false) AiRequests.EligibilityRequest request) {
        return eligibilityService.evaluate(user.id(), pblancId, request == null ? null : request.toFacts());
    }
}
