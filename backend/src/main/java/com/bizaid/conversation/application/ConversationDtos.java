package com.bizaid.conversation.application;

import com.bizaid.conversation.domain.Conversation;
import com.bizaid.conversation.domain.MessageRole;
import com.fasterxml.jackson.databind.JsonNode;
import java.time.Instant;

public final class ConversationDtos {

    private ConversationDtos() {
    }

    public record ConversationResponse(Long id, String title, Instant createdAt, Instant updatedAt) {

        public static ConversationResponse from(Conversation conversation) {
            return new ConversationResponse(conversation.getId(), conversation.getTitle(), conversation.getCreatedAt(),
                    conversation.getUpdatedAt());
        }
    }

    public record StartedQuestion(Long conversationId, MessageResponse message) {
    }

    /** resultType·result는 ASSISTANT 메시지에만 있다. result는 저장된 AI 결과 JSON을 그대로 돌려 화면을 복원한다. */
    public record MessageResponse(Long id, MessageRole role, String content, String resultType, JsonNode result,
                                  Instant createdAt) {
    }
}
