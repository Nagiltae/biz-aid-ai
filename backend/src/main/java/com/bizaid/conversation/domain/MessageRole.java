package com.bizaid.conversation.domain;

/** 메시지 작성 주체. ASSISTANT 메시지는 AI 응답을 받았을 때 서버만 저장하며 사용자가 API로 만들 수 없다. */
public enum MessageRole {
    USER,
    ASSISTANT
}
