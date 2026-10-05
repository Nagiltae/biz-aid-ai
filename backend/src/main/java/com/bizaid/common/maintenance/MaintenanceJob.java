package com.bizaid.common.maintenance;

import com.bizaid.ai.domain.AiWorkflow;
import com.bizaid.ai.infrastructure.AiWorkflowRepository;
import com.bizaid.auth.application.TrialService;
import com.bizaid.auth.infrastructure.AuthProperties;
import com.bizaid.auth.infrastructure.LoginThrottleRepository;
import com.bizaid.auth.infrastructure.RefreshTokenRepository;
import com.bizaid.usage.infrastructure.UsageCounterStore;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import org.springframework.beans.factory.annotation.Value;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

/**
 * 서비스 데이터 정리 스케줄러.
 * <ul>
 *   <li>IMP-016: 만료·폐기된 지 보관 기간이 지난 Refresh Token 삭제</li>
 *   <li>IMP-021: 실행 중 서버가 멈춰 남은 오래된 단계 점유 해제, 오래 방치된 진행 중 흐름 만료(FAILED), 끝난 흐름 보관 기간 뒤 삭제</li>
 *   <li>잠금이 끝난 로그인 시도 제한 행 삭제</li>
 *   <li>묶음5-1: 생성 24시간이 지난 체험 계정과 그 데이터 삭제(매시), 7일 지난 하루 사용 횟수 행 삭제</li>
 * </ul>
 * BOUNDARY: 진행 중(IN_PROGRESS·WAITING_FOR_USER) 흐름은 지우지 않고 만료 상태로만 바꾼다. 기업정보·대화는 건드리지 않는다.
 */
@Component
public class MaintenanceJob {

    private static final Logger log = LoggerFactory.getLogger(MaintenanceJob.class);
    private static final List<String> ACTIVE = List.of("IN_PROGRESS", "WAITING_FOR_USER");

    private final RefreshTokenRepository refreshTokens;
    private final LoginThrottleRepository loginThrottles;
    private final AiWorkflowRepository workflows;
    private final MaintenanceProperties properties;
    private final AuthProperties authProperties;
    private final ObjectMapper objectMapper;
    private final Clock clock;
    private final TrialService trials;
    private final UsageCounterStore usageCounters;
    private final ZoneId serviceZone;

    public MaintenanceJob(RefreshTokenRepository refreshTokens, LoginThrottleRepository loginThrottles, AiWorkflowRepository workflows,
                          MaintenanceProperties properties, AuthProperties authProperties, ObjectMapper objectMapper, Clock clock,
                          TrialService trials, UsageCounterStore usageCounters, @Value("${bizaid.service-zone}") String zone) {
        this.serviceZone = ZoneId.of(zone);
        this.trials = trials;
        this.usageCounters = usageCounters;
        this.refreshTokens = refreshTokens;
        this.loginThrottles = loginThrottles;
        this.workflows = workflows;
        this.properties = properties;
        this.authProperties = authProperties;
        this.objectMapper = objectMapper;
        this.clock = clock;
        // RISK: 보관 기간이 Refresh Token 수명보다 짧으면 아직 쓸 수 있는 폐기 기록을 지워 재사용 탐지가 약해진다.
        if (properties.refreshTokenRetention().compareTo(authProperties.jwt().refreshTokenTtl()) <= 0) {
            throw new IllegalStateException("bizaid.maintenance.refresh-token-retention must exceed the refresh token TTL");
        }
    }

    @Scheduled(cron = "${bizaid.maintenance.cron}", zone = "${bizaid.service-zone}")
    @Transactional
    public void scheduledDaily() {
        daily();
    }

    /** 하루 1회 정리. 테스트와 운영 점검에서 직접 호출할 수 있게 결과 건수를 돌려준다. */
    @Transactional
    public Summary daily() {
        Instant now = clock.instant();
        int tokens = refreshTokens.deleteExpiredOrRevokedBefore(now.minus(properties.refreshTokenRetention()));
        int throttles = loginThrottles.deleteIdleBefore(now.minus(properties.loginThrottleRetention()));
        int expired = expireInactive(now);
        int finished = workflows.deleteFinishedBefore(now.minus(properties.finishedWorkflowRetention()));
        int trialUsers = trials.purgeExpired(now);
        int usageRows = usageCounters.deleteBefore(now.atZone(serviceZone).toLocalDate().minus(properties.usageCounterRetention()));
        Summary summary = new Summary(tokens, throttles, expired, finished, releaseStaleClaims(now), trialUsers, usageRows);
        log.info("maintenance done refreshTokensDeleted={} loginThrottlesDeleted={} workflowsExpired={} workflowsDeleted={} staleClaims={} "
                        + "trialUsersDeleted={} usageRowsDeleted={}",
                summary.refreshTokensDeleted(), summary.loginThrottlesDeleted(), summary.workflowsExpired(),
                summary.workflowsDeleted(), summary.staleClaimsReleased(), summary.trialUsersDeleted(), summary.usageRowsDeleted());
        return summary;
    }

    /** 매시: 생성 ttl(24시간)이 지난 체험 계정을 지운다. 하루 1회만 돌면 최대 48시간까지 남을 수 있어 따로 자주 돈다. */
    @Scheduled(cron = "${bizaid.maintenance.trial-cron}", zone = "${bizaid.service-zone}")
    public void scheduledTrialCleanup() {
        int deleted = trials.purgeExpired(clock.instant());
        if (deleted > 0) {
            log.info("trial cleanup done trialUsersDeleted={}", deleted);
        }
    }

    /** 5분마다: 점유 시간이 지난 단계 점유를 푼다. 늦게 끝난 이전 요청은 version 불일치로 저장을 거부하므로 안전하다. */
    @Scheduled(cron = "${bizaid.maintenance.stale-step-cron}", zone = "${bizaid.service-zone}")
    @Transactional
    public void releaseStaleClaims() {
        releaseStaleClaims(clock.instant());
    }

    private int releaseStaleClaims(Instant now) {
        List<AiWorkflow> stale = workflows.findByStepStartedAtBefore(now.minus(AiWorkflow.STALE_STEP));
        stale.forEach(AiWorkflow::clearStaleClaim);
        return stale.size();
    }

    private int expireInactive(Instant now) {
        List<AiWorkflow> inactive = workflows.findByStatusInAndUpdatedAtBefore(ACTIVE, now.minus(properties.workflowInactiveExpiry()));
        for (AiWorkflow workflow : inactive) {
            workflow.expire(expiredState(workflow.getStateJson()), now);
        }
        return inactive.size();
    }

    // State JSON과 column의 상태가 항상 같아야 하므로 JSON 안의 상태도 같은 값으로 바꾼다(FastAPI가 쓰는 snake_case 이름 그대로).
    private String expiredState(String stateJson) {
        try {
            ObjectNode state = (ObjectNode) objectMapper.readTree(stateJson);
            state.put("status", "FAILED");
            state.put("current_step", "FAILED");
            state.put("next_action", "NONE");
            state.put("failure_code", "workflow_expired");
            state.putArray("pending");
            return objectMapper.writeValueAsString(state);
        } catch (Exception exception) {
            throw new IllegalStateException("workflow state is not a JSON object", exception);
        }
    }

    public record Summary(int refreshTokensDeleted, int loginThrottlesDeleted, int workflowsExpired, int workflowsDeleted,
                          int staleClaimsReleased, int trialUsersDeleted, int usageRowsDeleted) {
    }
}
