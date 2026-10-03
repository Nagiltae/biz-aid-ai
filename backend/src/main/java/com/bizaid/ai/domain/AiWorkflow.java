package com.bizaid.ai.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;
import java.time.Duration;
import java.time.Instant;

/**
 * AI 추천 흐름(LangGraph State)의 요청 간 저장 단위.
 * state_json은 FastAPI가 돌려준 State 그대로이고, status·current_step은 그 State에서 복사한 조회용 값이다.
 * 두 값이 어긋나지 않도록 상태 변경은 applyState() 한 곳에서만 한다.
 */
@Entity
@Table(name = "ai_workflows")
public class AiWorkflow {

    /** 단계 실행 중 점유가 이 시간보다 오래되면 중단된 실행으로 보고 다시 점유할 수 있다(한 단계는 Spring 제한 90초 이내). */
    public static final Duration STALE_STEP = Duration.ofMinutes(5);

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "user_id", nullable = false)
    private Long userId;

    @Column(nullable = false, length = 20)
    private String status;

    @Column(name = "current_step", nullable = false, length = 40)
    private String currentStep;

    /** 실제 column은 MySQL JSON(V9)이다. length는 테스트용 H2 schema 생성에만 쓰인다. */
    @Column(name = "state_json", nullable = false, length = 1_000_000)
    private String stateJson;

    @Version
    @Column(nullable = false)
    private Long version;

    @Column(name = "step_started_at")
    private Instant stepStartedAt;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    protected AiWorkflow() {
    }

    public AiWorkflow(Long userId, String stateJson, String status, String currentStep, Instant now) {
        this.userId = userId;
        this.createdAt = now;
        applyState(stateJson, status, currentStep, now);
    }

    /** FastAPI가 돌려준 새 State를 저장한다. 점유도 함께 푼다. */
    public void applyState(String stateJson, String status, String currentStep, Instant now) {
        this.stateJson = stateJson;
        this.status = status;
        this.currentStep = currentStep;
        this.stepStartedAt = null;
        this.updatedAt = now;
    }

    public boolean isBusy(Instant now) {
        return stepStartedAt != null && stepStartedAt.plus(STALE_STEP).isAfter(now);
    }

    /** 다음 단계 실행을 점유한다. 저장 시 version이 바뀌므로 같은 버전을 읽은 다른 요청의 점유는 실패한다. */
    public void claimStep(Instant now) {
        this.stepStartedAt = now;
        this.updatedAt = now;
    }

    public void releaseStep(Instant now) {
        this.stepStartedAt = null;
        this.updatedAt = now;
    }

    /** IMP-021: 중단된 실행이 남긴 오래된 점유만 푼다. 사용자 활동이 아니므로 updated_at은 바꾸지 않는다. */
    public void clearStaleClaim() {
        this.stepStartedAt = null;
    }

    /** IMP-021: 오래 방치된 진행 중 흐름을 만료(FAILED)로 끝낸다. State JSON의 상태와 column을 같게 맞춘다. */
    public void expire(String stateJson, Instant now) {
        applyState(stateJson, "FAILED", "FAILED", now);
    }

    public boolean isOwnedBy(Long userId) {
        return this.userId.equals(userId);
    }

    public Long getId() {
        return id;
    }

    public String getStatus() {
        return status;
    }

    public String getStateJson() {
        return stateJson;
    }

    public Long getVersion() {
        return version;
    }

    public String getCurrentStep() {
        return currentStep;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }
}
