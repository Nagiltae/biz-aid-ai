package com.bizaid.ai.application;

import com.fasterxml.jackson.databind.JsonNode;
import java.util.Map;

import com.bizaid.ai.infrastructure.HttpAiGateway;

/**
 * Spring이 AI 기능을 호출하는 유일한 경계(AI 연결 창구).
 * 구현(HttpAiGateway)은 FastAPI 내부 API(POST /internal/v1/query, POST /internal/v1/eligibility)를 HTTP로 호출한다.
 * Controller·Service는 이 인터페이스만 알아서 AI 호출 방식이 바뀌어도 호출 쪽 코드는 바뀌지 않고, 테스트에서는 가짜 서버로 대체할 수 있다.
 */
public interface AiGateway {

    AiDtos.AiQueryResult query(String query);

    default AiDtos.AiQueryResult query(String query, String selectedPblancId) {
        if (selectedPblancId == null) {
            return query(query);
        }
        throw new UnsupportedOperationException("공고 선택을 지원하지 않는 연결 창구입니다.");
    }

    default AiDtos.AiQueryResult query(String query, String selectedPblancId, String companyRegion) {
        if (companyRegion == null) {
            return query(query, selectedPblancId);
        }
        throw new UnsupportedOperationException("기업 지역 전달을 지원하지 않는 연결 창구입니다.");
    }

    AiDtos.EligibilityResult evaluateEligibility(AiDtos.EligibilityCommand command);

    AiDtos.PersonalizedSearchResult personalizedSearch(AiDtos.PersonalizedSearchCommand command);

    AiDtos.PersonalizedEligibilityResult personalizedEligibility(AiDtos.PersonalizedEligibilityCommand command);

    /** V2-3 흐름 시작: 개인화 검색과 Top 3 확정까지(판정 없음). 반환값은 저장할 State JSON이다. */
    JsonNode startWorkflow(AiDtos.PersonalizedEligibilityCommand command);

    /** 저장된 State로 다음 한 단계 실행(command: continue / answer). 판정 LLM 호출은 최대 1건이다. */
    JsonNode advanceWorkflow(JsonNode state, String command, Map<String, Object> answers);
}
