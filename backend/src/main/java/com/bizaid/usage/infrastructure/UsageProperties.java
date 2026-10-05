package com.bizaid.usage.infrastructure;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * 하루 사용 제한과 체험 계정 설정(2026-10-04 묶음5-1 사용자 결정).
 * dailyLimit: 사용자별 하루 AI 사용 횟수. trial.*: 체험하기 on/off, 체험 계정 수명, 체험 전체 하루 AI 합산 상한, 접속 IP별 하루 체험 계정 생성 수.
 */
@ConfigurationProperties(prefix = "bizaid.usage")
public record UsageProperties(int dailyLimit, int dailyLimitPerIp, int globalDailyLimit, int signupPerIpPerDay, Trial trial) {

    public record Trial(boolean enabled, Duration ttl, int dailyPoolLimit, int maxCreatesPerIpPerDay) {
    }
}
