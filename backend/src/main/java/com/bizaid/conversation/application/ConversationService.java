package com.bizaid.conversation.application;

import com.bizaid.activity.application.ActivityLogService;
import com.bizaid.activity.domain.ActivityAction;
import com.bizaid.common.error.ApiException;
import com.bizaid.common.error.ErrorCode;
import com.bizaid.company.application.CompanyService;
import com.bizaid.conversation.domain.Conversation;
import com.bizaid.conversation.domain.Message;
import com.bizaid.conversation.domain.MessageRole;
import com.bizaid.conversation.infrastructure.ConversationRepository;
import com.bizaid.conversation.infrastructure.MessageRepository;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Clock;
import java.time.Instant;
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 대화와 메시지 저장·조회.
 * 다른 사용자의 대화는 존재 여부도 알려 주지 않도록 "없음"과 같은 오류로 처리한다.
 * 대화·AI 검색은 로그인 사용자에게 제공한다. 기업정보 없는 검색은 지역 필터 없이 실행한다.
 */
@Service
public class ConversationService {

    static final String DEFAULT_TITLE = "새 대화";
    static final int TITLE_FROM_QUESTION = 40;

    private final ConversationRepository conversations;
    private final MessageRepository messages;
    private final ObjectMapper objectMapper;
    private final Clock clock;
    private final ActivityLogService activityLog;
    private final CompanyService companyService;

    public ConversationService(ConversationRepository conversations, MessageRepository messages, ObjectMapper objectMapper,
                               Clock clock, ActivityLogService activityLog, CompanyService companyService) {
        this.conversations = conversations;
        this.messages = messages;
        this.objectMapper = objectMapper;
        this.clock = clock;
        this.activityLog = activityLog;
        this.companyService = companyService;
    }

    @Transactional
    public ConversationDtos.ConversationResponse create(Long userId, String title) {
        String value = title == null || title.isBlank() ? DEFAULT_TITLE : title.strip();
        Conversation conversation = conversations.save(new Conversation(userId, value, clock.instant()));
        activityLog.success(ActivityAction.CONVERSATION_CREATE, userId, "CONVERSATION", conversation.getId(), null);
        return ConversationDtos.ConversationResponse.from(conversation);
    }

    @Transactional(readOnly = true)
    public List<ConversationDtos.ConversationResponse> list(Long userId) {
        return conversations.findTop50ByUserIdOrderByUpdatedAtDescIdDesc(userId).stream()
                .map(ConversationDtos.ConversationResponse::from).toList();
    }

    @Transactional(readOnly = true)
    public List<ConversationDtos.MessageResponse> messages(Long userId, Long conversationId) {
        owned(userId, conversationId);
        return messages.findByConversationIdOrderByIdAsc(conversationId).stream().map(this::toResponse).toList();
    }

    /** 사용자 질문 저장. */
    @Transactional
    public ConversationDtos.MessageResponse addUserMessage(Long userId, Long conversationId, String content) {
        return append(owned(userId, conversationId), MessageRole.USER, content.strip(), null, null);
    }

    /**
     * AI 질문 시작: 대화를 고르거나(없으면 첫 질문 앞부분을 제목으로 새로 만들고) 사용자 질문을 먼저 저장한다.
     * AI 호출 전에 별도 트랜잭션으로 저장해 AI가 실패해도 질문 기록은 남는다.
     */
    @Transactional
    public ConversationDtos.StartedQuestion startQuestion(Long userId, Long conversationId, String question) {
        // BOUNDARY: 기업정보는 검색의 optional 지역 조건이다. 사용자 소유권 검증은 그대로 유지한다.
        String text = question.strip();
        Conversation conversation;
        if (conversationId == null) {
            conversation = conversations.save(new Conversation(userId, text.length() > TITLE_FROM_QUESTION
                    ? text.substring(0, TITLE_FROM_QUESTION) : text, clock.instant()));
            activityLog.success(ActivityAction.CONVERSATION_CREATE, userId, "CONVERSATION", conversation.getId(), null);
        } else {
            conversation = owned(userId, conversationId);
        }
        return new ConversationDtos.StartedQuestion(conversation.getId(), append(conversation, MessageRole.USER, text, null, null));
    }

    /**
     * AI 응답 성공 때만 호출한다(실패 시 가짜 ASSISTANT 메시지를 만들지 않는다).
     * content는 AI가 쓴 자연어 답변이며, 자연어 답이 없는 목록 결과(SEARCH_LIST)는 빈 문자열로 둔다. Spring이 답변 문장을 지어내지 않는다.
     * 구조화 결과는 AI 응답 DTO를 그대로 JSON으로 보존해 대화 재조회 때 같은 화면을 복원한다.
     */
    @Transactional
    public ConversationDtos.MessageResponse addAssistantMessage(Long userId, Long conversationId, String content,
                                                                String resultType, Object result) {
        String json;
        try {
            json = objectMapper.writeValueAsString(result);
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException(exception);
        }
        return append(owned(userId, conversationId), MessageRole.ASSISTANT, content == null ? "" : content, resultType, json);
    }

    private ConversationDtos.MessageResponse append(Conversation conversation, MessageRole role, String content,
                                                    String resultType, String resultJson) {
        Instant now = clock.instant();
        conversation.touch(now);
        return toResponse(messages.save(new Message(conversation, role, content, resultType, resultJson, now)));
    }

    private ConversationDtos.MessageResponse toResponse(Message message) {
        JsonNode result = null;
        if (message.getAiResultJson() != null) {
            try {
                result = objectMapper.readTree(message.getAiResultJson());
            } catch (JsonProcessingException exception) {
                throw new IllegalStateException(exception);
            }
        }
        return new ConversationDtos.MessageResponse(message.getId(), message.getRole(), message.getContent(),
                message.getAiResultType(), result, message.getCreatedAt());
    }

    private Conversation owned(Long userId, Long conversationId) {
        return conversations.findById(conversationId).filter(conversation -> conversation.isOwnedBy(userId))
                .orElseThrow(() -> new ApiException(ErrorCode.CONVERSATION_NOT_FOUND));
    }
}
