package com.bizaid.ai;

import org.springframework.stereotype.Service;

/**
 * AI 지원사업 검색·질문의 Application Service.
 * 자연어 조건 추출·MySQL 후보 선택·근거 검색·답변 생성은 모두 FastAPI(Python AI 서비스)가 한다. Java로 다시 구현하지 않는다.
 */
@Service
public class AiQueryService {

    private final AiGateway aiGateway;

    public AiQueryService(AiGateway aiGateway) {
        this.aiGateway = aiGateway;
    }

    public AiDtos.AiQueryResult query(String query) {
        return aiGateway.query(query.strip());
    }
}
