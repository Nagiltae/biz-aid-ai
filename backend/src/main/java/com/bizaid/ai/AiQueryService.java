package com.bizaid.ai;

import com.bizaid.conversation.ConversationDtos;
import com.bizaid.conversation.ConversationService;
import org.springframework.stereotype.Service;

/**
 * AI 지원사업 검색·질문의 Application Service.
 * 흐름: 사용자 질문 저장 → FastAPI 호출(AiGateway) → 성공 시 ASSISTANT 메시지 저장.
 * 자연어 조건 추출·MySQL 후보·근거 검색·답변 생성은 모두 FastAPI(Python AI 서비스)가 한다. Java로 다시 구현하지 않는다.
 * 이 메서드에는 트랜잭션을 두지 않는다. 수십 초 걸리는 AI 호출 동안 DB 연결을 잡고 있지 않게 저장 단계마다 짧은 트랜잭션을 쓴다.
 */
@Service
public class AiQueryService {

    private final AiGateway aiGateway;
    private final ConversationService conversationService;

    public AiQueryService(AiGateway aiGateway, ConversationService conversationService) {
        this.aiGateway = aiGateway;
        this.conversationService = conversationService;
    }

    public AiDtos.AiQueryResponse query(Long userId, AiDtos.AiQueryRequest request) {
        ConversationDtos.StartedQuestion started = conversationService.startQuestion(userId, request.conversationId(),
                request.query());
        Long conversationId = started.conversationId();
        // 실패하면 여기서 예외가 올라가고 ASSISTANT 메시지는 저장되지 않는다(질문만 남는다).
        AiDtos.AiQueryResult result = aiGateway.query(request.query().strip());
        // DOCUMENT_QA는 AI가 쓴 답변을 본문으로, SEARCH_LIST는 자연어 답이 없으므로 본문을 비우고 구조화 결과만 저장한다.
        ConversationDtos.MessageResponse answer = conversationService.addAssistantMessage(userId, conversationId,
                result.answer(), result.requestMode(), result);
        return new AiDtos.AiQueryResponse(conversationId, started.message(), answer, result);
    }
}
