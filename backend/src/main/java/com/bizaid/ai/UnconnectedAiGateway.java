package com.bizaid.ai;

import com.bizaid.common.ApiException;
import com.bizaid.common.ErrorCode;
import org.springframework.stereotype.Component;

/**
 * FastAPI 연결 전 단계의 AiGateway.
 * BOUNDARY: 가짜 검색 결과나 가짜 ELIGIBLE을 만들지 않는다. 항상 ai_service_not_connected(503)를 돌려
 * 화면이 "AI 연결 준비 중"을 정직하게 표시하게 한다. FastAPI 연결 작업에서 HTTP 구현으로 교체한다.
 */
@Component
public class UnconnectedAiGateway implements AiGateway {

    @Override
    public AiDtos.AiQueryResult query(String query) {
        throw new ApiException(ErrorCode.AI_SERVICE_NOT_CONNECTED);
    }

    @Override
    public AiDtos.EligibilityResult evaluateEligibility(AiDtos.EligibilityCommand command) {
        throw new ApiException(ErrorCode.AI_SERVICE_NOT_CONNECTED);
    }
}
