package com.bizaid.auth.infrastructure;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

/** 로그인 시도 제한 기준(사용자 결정 2026-10-04: 계정·IP 각각 5회 연속 실패 → 10분 잠금). */
@ConfigurationProperties(prefix = "bizaid.login-throttle")
public record LoginThrottleProperties(int maxFailures, Duration lockDuration) {
}
