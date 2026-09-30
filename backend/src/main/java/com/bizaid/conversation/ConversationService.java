package com.bizaid.conversation;

import com.bizaid.common.ApiException;
import com.bizaid.common.ErrorCode;
import java.time.Clock;
import java.time.Instant;
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 대화와 메시지 저장·조회.
 * 다른 사용자의 대화는 존재 여부도 알려 주지 않도록 "없음"과 같은 오류로 처리한다.
 */
@Service
public class ConversationService {

    static final String DEFAULT_TITLE = "새 대화";

    private final ConversationRepository conversations;
    private final MessageRepository messages;
    private final Clock clock;

    public ConversationService(ConversationRepository conversations, MessageRepository messages, Clock clock) {
        this.conversations = conversations;
        this.messages = messages;
        this.clock = clock;
    }

    @Transactional
    public ConversationDtos.ConversationResponse create(Long userId, String title) {
        String value = title == null || title.isBlank() ? DEFAULT_TITLE : title.strip();
        return ConversationDtos.ConversationResponse.from(conversations.save(new Conversation(userId, value, clock.instant())));
    }

    @Transactional(readOnly = true)
    public List<ConversationDtos.ConversationResponse> list(Long userId) {
        return conversations.findTop50ByUserIdOrderByUpdatedAtDescIdDesc(userId).stream()
                .map(ConversationDtos.ConversationResponse::from).toList();
    }

    @Transactional(readOnly = true)
    public List<ConversationDtos.MessageResponse> messages(Long userId, Long conversationId) {
        owned(userId, conversationId);
        return messages.findByConversationIdOrderByIdAsc(conversationId).stream()
                .map(ConversationDtos.MessageResponse::from).toList();
    }

    /** 사용자 질문 저장. ASSISTANT 메시지는 AI 연결 단계에서 서버가 같은 방식으로 저장한다. */
    @Transactional
    public ConversationDtos.MessageResponse addUserMessage(Long userId, Long conversationId, String content) {
        return append(owned(userId, conversationId), MessageRole.USER, content.strip());
    }

    private ConversationDtos.MessageResponse append(Conversation conversation, MessageRole role, String content) {
        Instant now = clock.instant();
        conversation.touch(now);
        return ConversationDtos.MessageResponse.from(messages.save(new Message(conversation, role, content, now)));
    }

    private Conversation owned(Long userId, Long conversationId) {
        return conversations.findById(conversationId).filter(conversation -> conversation.isOwnedBy(userId))
                .orElseThrow(() -> new ApiException(ErrorCode.CONVERSATION_NOT_FOUND));
    }
}
