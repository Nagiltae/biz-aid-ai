package com.bizaid.auth.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Duration;
import java.time.Instant;

/** 계정(이메일) 또는 접속 IP 하나의 연속 로그인 실패 상태. 원문 대신 SHA-256 key만 둔다. */
@Entity
@Table(name = "login_throttles")
public class LoginThrottle {

    @Id
    @Column(name = "throttle_key", length = 64)
    private String throttleKey;

    @Column(name = "key_type", nullable = false, length = 10)
    private String keyType;

    @Column(name = "failure_count", nullable = false)
    private int failureCount;

    @Column(name = "locked_until")
    private Instant lockedUntil;

    @Column(name = "last_failure_at", nullable = false)
    private Instant lastFailureAt;

    protected LoginThrottle() {
    }

    public LoginThrottle(String throttleKey, String keyType, Instant now) {
        this.throttleKey = throttleKey;
        this.keyType = keyType;
        this.lastFailureAt = now;
    }

    public boolean isLocked(Instant now) {
        return lockedUntil != null && lockedUntil.isAfter(now);
    }

    /** 실패 1회를 더한다. 기준 횟수에 닿으면 잠그고 횟수를 0으로 되돌린다(잠금이 끝나면 다시 5회를 센다). */
    public void recordFailure(Instant now, int maxFailures, Duration lockDuration) {
        if (lockedUntil != null && !lockedUntil.isAfter(now)) {
            lockedUntil = null;
        }
        failureCount++;
        lastFailureAt = now;
        if (failureCount >= maxFailures) {
            lockedUntil = now.plus(lockDuration);
            failureCount = 0;
        }
    }

    public String getThrottleKey() {
        return throttleKey;
    }
}
