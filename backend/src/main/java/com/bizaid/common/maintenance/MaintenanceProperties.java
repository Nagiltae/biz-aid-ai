package com.bizaid.common.maintenance;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * 정리 작업 주기와 보관 기간(IMP-016·021).
 * refreshTokenRetention은 Refresh Token 수명(14일)보다 길어야 폐기 기록으로 재사용(탈취) 탐지를 계속할 수 있다.
 */
@ConfigurationProperties(prefix = "bizaid.maintenance")
public record MaintenanceProperties(String cron, String staleStepCron, Duration refreshTokenRetention, Duration loginThrottleRetention,
                                    Duration workflowInactiveExpiry, Duration finishedWorkflowRetention) {
}
