package com.bizaid.common.maintenance;

import java.time.Duration;
import java.time.Period;
import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * 정리 작업 주기와 보관 기간(IMP-016·021).
 * usageCounterRetention: 하루 사용 횟수 행을 날짜 기준으로 남기는 기간(묶음5-1, 7일).
 * refreshTokenRetention은 Refresh Token 수명(14일)보다 길어야 폐기 기록으로 재사용(탈취) 탐지를 계속할 수 있다.
 */
@ConfigurationProperties(prefix = "bizaid.maintenance")
public record MaintenanceProperties(String cron, String staleStepCron, String trialCron, Duration refreshTokenRetention,
                                    Duration loginThrottleRetention, Duration workflowInactiveExpiry, Duration finishedWorkflowRetention,
                                    Period usageCounterRetention) {
}
