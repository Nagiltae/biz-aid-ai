package com.bizaid.ai.application;

import com.bizaid.ai.infrastructure.HttpAiGateway;

/**
 * Spring이 AI 기능을 호출하는 유일한 경계(AI 연결 창구).
 * 구현(HttpAiGateway)은 FastAPI 내부 API(POST /internal/v1/query, POST /internal/v1/eligibility)를 HTTP로 호출한다.
 * Controller·Service는 이 인터페이스만 알아서 AI 호출 방식이 바뀌어도 호출 쪽 코드는 바뀌지 않고, 테스트에서는 가짜 서버로 대체할 수 있다.
 */
public interface AiGateway {

    AiDtos.AiQueryResult query(String query);

    AiDtos.EligibilityResult evaluateEligibility(AiDtos.EligibilityCommand command);

    AiDtos.PersonalizedSearchResult personalizedSearch(AiDtos.PersonalizedSearchCommand command);

    AiDtos.PersonalizedEligibilityResult personalizedEligibility(AiDtos.PersonalizedEligibilityCommand command);
}
