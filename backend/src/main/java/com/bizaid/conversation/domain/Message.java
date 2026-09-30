package com.bizaid.conversation.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import java.time.Instant;

/**
 * 대화에 속한 메시지 한 건.
 * 대화와는 LAZY 다대일로 연결한다. 메시지 목록은 대화 id로 한 번에 조회하고 응답 DTO로 바꾸므로 대화를 다시 읽지 않는다.
 */
@Entity
@Table(name = "messages")
public class Message {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "conversation_id", nullable = false)
    private Conversation conversation;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private MessageRole role;

    // 실제 column은 MEDIUMTEXT(V6)다. length는 테스트용 H2 schema 생성에만 쓰인다.
    @Column(nullable = false, length = 65535)
    private String content;

    /** ASSISTANT 메시지의 AI 결과 종류(FastAPI request_mode: SEARCH_LIST / DOCUMENT_QA). USER 메시지는 null. */
    @Column(name = "ai_result_type", length = 20)
    private String aiResultType;

    /** 화면 복원용 AI 구조화 결과 JSON(공고 카드·답변·근거). 실제 column은 JSON(V7), length는 테스트용 H2 schema에만 쓰인다. */
    @Column(name = "ai_result_json", length = 1_000_000)
    private String aiResultJson;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected Message() {
    }

    public Message(Conversation conversation, MessageRole role, String content, Instant now) {
        this(conversation, role, content, null, null, now);
    }

    public Message(Conversation conversation, MessageRole role, String content, String aiResultType, String aiResultJson,
                   Instant now) {
        this.conversation = conversation;
        this.role = role;
        this.content = content;
        this.aiResultType = aiResultType;
        this.aiResultJson = aiResultJson;
        this.createdAt = now;
    }

    public Long getId() {
        return id;
    }

    public MessageRole getRole() {
        return role;
    }

    public String getContent() {
        return content;
    }

    public String getAiResultType() {
        return aiResultType;
    }

    public String getAiResultJson() {
        return aiResultJson;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
