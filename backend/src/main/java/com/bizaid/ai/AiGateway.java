package com.bizaid.ai;

/**
 * Spring이 AI 기능을 호출하는 유일한 경계.
 * 다음 단계에서 FastAPI 내부 API(POST /internal/v1/query, POST /internal/v1/eligibility)를 HTTP로 호출하는 구현으로 교체한다.
 * Controller·Service는 이 인터페이스만 알기 때문에 FastAPI 연결 시 호출 쪽 코드는 바뀌지 않는다.
 */
public interface AiGateway {

    AiDtos.AiQueryResult query(String query);

    AiDtos.EligibilityResult evaluateEligibility(AiDtos.EligibilityCommand command);
}
