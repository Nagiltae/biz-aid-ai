package com.bizaid.conversation.presentation;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

/** 대화 HTTP 요청 DTO. 입력 검증(Bean Validation)은 HTTP 경계에서 한다. */
public final class ConversationRequests {

    private ConversationRequests() {
    }

    /** 제목을 비우면 "새 대화"로 저장한다. React는 첫 질문의 앞부분을 제목으로 보낸다. */
    public record CreateConversationRequest(@Size(max = 200, message = "제목은 200자 이하로 입력해 주세요.") String title) {
    }

    public record CreateMessageRequest(
            @NotBlank(message = "메시지를 입력해 주세요.") @Size(max = 2000, message = "메시지는 2000자 이하로 입력해 주세요.")
            String content) {
    }
}
