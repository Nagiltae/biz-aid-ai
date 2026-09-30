package com.bizaid.activity.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;

/**
 * 사용자 활동 한 건. 쓰기만 하고 수정하지 않는 기록이다.
 * BOUNDARY: 비밀번호·토큰·키 같은 비밀값과 질문·답변 전문은 넣지 않는다. 대화 내용의 기준 저장소는 messages다.
 */
@Entity
@Table(name = "activity_logs")
public class ActivityLog {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "user_id")
    private Long userId;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 40)
    private ActivityAction action;

    @Column(name = "target_type", length = 40)
    private String targetType;

    @Column(name = "target_id", length = 80)
    private String targetId;

    @Column(nullable = false)
    private boolean success;

    @Column(name = "error_code", length = 80)
    private String errorCode;

    /** 실제 column은 JSON(V8)이다. length는 테스트용 H2 schema 생성에만 쓰인다. */
    @Column(name = "metadata_json", length = 4000)
    private String metadataJson;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected ActivityLog() {
    }

    public ActivityLog(Long userId, ActivityAction action, String targetType, String targetId, boolean success, String errorCode,
                       String metadataJson, Instant createdAt) {
        this.userId = userId;
        this.action = action;
        this.targetType = targetType;
        this.targetId = targetId;
        this.success = success;
        this.errorCode = errorCode;
        this.metadataJson = metadataJson;
        this.createdAt = createdAt;
    }

    public Long getUserId() {
        return userId;
    }

    public ActivityAction getAction() {
        return action;
    }

    public String getTargetType() {
        return targetType;
    }

    public String getTargetId() {
        return targetId;
    }

    public boolean isSuccess() {
        return success;
    }

    public String getErrorCode() {
        return errorCode;
    }

    public String getMetadataJson() {
        return metadataJson;
    }
}
