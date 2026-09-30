package com.bizaid.ai.application;

import com.bizaid.activity.application.ActivityLogService;
import com.bizaid.activity.domain.ActivityAction;
import com.bizaid.common.error.ApiException;
import com.bizaid.conversation.application.ConversationDtos;
import com.bizaid.conversation.application.ConversationService;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.stereotype.Service;

/**
 * AI 지원사업 검색·질문의 Application Service.
 * 흐름: 사용자 질문 저장 → FastAPI 호출(AiGateway) → 성공 시 ASSISTANT 메시지 저장 → 활동 기록.
 * 자연어 조건 추출·MySQL 후보·근거 검색·답변 생성은 모두 FastAPI(Python AI 서비스)가 한다. Java로 다시 구현하지 않는다.
 * 이 메서드에는 트랜잭션을 두지 않는다. 수십 초 걸리는 AI 호출 동안 DB 연결을 잡고 있지 않게 저장 단계마다 짧은 트랜잭션을 쓴다.
 */
@Service
public class AiQueryService {

    private final AiGateway aiGateway;
    private final ConversationService conversationService;
    private final ActivityLogService activityLog;

    public AiQueryService(AiGateway aiGateway, ConversationService conversationService, ActivityLogService activityLog) {
        this.aiGateway = aiGateway;
        this.conversationService = conversationService;
        this.activityLog = activityLog;
    }

    public AiDtos.AiQueryResponse query(Long userId, String query, Long requestedConversationId) {
        ConversationDtos.StartedQuestion started = conversationService.startQuestion(userId, requestedConversationId, query);
        Long conversationId = started.conversationId();
        AiDtos.AiQueryResult result;
        try {
            result = aiGateway.query(query.strip());
        } catch (ApiException exception) {
            // 실패하면 ASSISTANT 메시지는 저장하지 않는다(질문만 남는다). 활동 기록에도 질문 본문은 넣지 않는다.
            activityLog.failure(ActivityAction.AI_QUERY, userId, "CONVERSATION", conversationId, exception.errorCode().code(), null);
            throw exception;
        }
        // DOCUMENT_QA는 AI가 쓴 답변을 본문으로, SEARCH_LIST는 자연어 답이 없으므로 본문을 비우고 구조화 결과만 저장한다.
        ConversationDtos.MessageResponse answer = conversationService.addAssistantMessage(userId, conversationId,
                result.answer(), result.requestMode(), result);
        Map<String, Object> metadata = new LinkedHashMap<>();
        metadata.put("requestMode", result.requestMode());
        metadata.put("status", result.status());
        if (result.programs() != null) {
            metadata.put("programCount", result.programs().size());
        }
        activityLog.success(ActivityAction.AI_QUERY, userId, "CONVERSATION", conversationId, metadata);
        return new AiDtos.AiQueryResponse(conversationId, started.message(), answer, result);
    }
}
