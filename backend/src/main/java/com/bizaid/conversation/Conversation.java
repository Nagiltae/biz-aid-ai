package com.bizaid.conversation;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;

/** 사용자와 AI 지원사업 검색·질문의 대화 묶음. 소유 사용자는 id로만 참조해 대화 조회 때 User를 함께 읽지 않는다. */
@Entity
@Table(name = "conversations")
public class Conversation {

    static final int TITLE_MAX = 200;

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "user_id", nullable = false)
    private Long userId;

    @Column(nullable = false, length = TITLE_MAX)
    private String title;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    protected Conversation() {
    }

    public Conversation(Long userId, String title, Instant now) {
        this.userId = userId;
        this.title = title;
        this.createdAt = now;
        this.updatedAt = now;
    }

    /** 새 메시지가 저장될 때 호출해 대화 목록이 최근 대화 순으로 정렬되게 한다. */
    void touch(Instant now) {
        this.updatedAt = now;
    }

    boolean isOwnedBy(Long userId) {
        return this.userId.equals(userId);
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }
}
