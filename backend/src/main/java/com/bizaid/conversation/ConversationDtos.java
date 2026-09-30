package com.bizaid.conversation;

import com.fasterxml.jackson.databind.JsonNode;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.time.Instant;

public final class ConversationDtos {

    private ConversationDtos() {
    }

    /** 제목을 비우면 "새 대화"로 저장한다. React는 첫 질문의 앞부분을 제목으로 보낸다. */
    public record CreateConversationRequest(@Size(max = 200, message = "제목은 200자 이하로 입력해 주세요.") String title) {
    }

    public record CreateMessageRequest(
            @NotBlank(message = "메시지를 입력해 주세요.") @Size(max = 2000, message = "메시지는 2000자 이하로 입력해 주세요.")
            String content) {
    }

    public record ConversationResponse(Long id, String title, Instant createdAt, Instant updatedAt) {

        static ConversationResponse from(Conversation conversation) {
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
