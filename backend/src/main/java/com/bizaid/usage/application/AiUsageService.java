package com.bizaid.usage.application;

import com.bizaid.auth.application.AuthService;
import com.bizaid.auth.domain.AuthUser;
import com.bizaid.common.error.ApiException;
import com.bizaid.common.error.ErrorCode;
import com.bizaid.usage.infrastructure.UsageCounterStore;
import com.bizaid.usage.infrastructure.UsageProperties;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.function.Supplier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

/**
 * 하루 AI 사용 제한(2026-10-04 묶음5-1 사용자 결정).
 * 사용자별 하루 dailyLimit회, 한국 시간 자정에 새로 센다. AI 검색 질문·맞춤 추천 시작·단일 자격 판정 1회를 1로 센다.
 * 추천의 다음 단계 진행·부족 정보 답변은 세지 않는다. 체험 계정은 체험 전체 합산 상한(TRIAL_POOL)도 함께 쓴다.
 *
 * <p>BOUNDARY: 트랜잭션을 두지 않는다. 각 증감은 DB 한 문장으로 바로 commit되고, IP·체험·서비스 합산에서 막히면 앞서 예약한 횟수를 되돌린다.
 * <p>EXCEPTION: AI가 결과를 주지 못한 요청(기업정보 없음·AI 시간 초과·예상 밖 실행 오류 등)은 횟수를 되돌린다.
 */
@Service
public class AiUsageService {

    public static final String TRIAL_POOL = "TRIAL_POOL";
    public static final String SERVICE_POOL = "SERVICE_POOL";

    private final UsageCounterStore store;
    private final UsageProperties properties;
    private final Clock clock;
    private final ZoneId zone;

    public AiUsageService(UsageCounterStore store, UsageProperties properties, Clock clock, @Value("${bizaid.service-zone}") String zone) {
        this.store = store;
        this.properties = properties;
        this.clock = clock;
        this.zone = ZoneId.of(zone);
    }

    /** 신뢰한 proxy를 거친 실제 IP로 모든 상한을 예약한 뒤에만 AI를 실행한다. */
    public <T> T run(AuthUser user, String clientIp, Supplier<T> action) {
        Instant now = clock.instant();
        LocalDate day = serviceDate(now);
        List<String> reserved = consume(user.id(), user.trial(), clientIp, now);
        try {
            return action.get();
        } catch (RuntimeException exception) {
            refund(reserved, day, clock.instant());
            throw exception;
        }
    }

    /** 계정 → IP → 체험(해당 계정) → 전체 순서. 이미 예약한 key만 실패 시 역순으로 되돌린다. */
    public List<String> consume(Long userId, boolean trial, String clientIp, Instant now) {
        LocalDate day = serviceDate(now);
        String ip = ipKey(clientIp);
        List<String> reserved = new ArrayList<>();
        try {
            reserve(reserved, userKey(userId), day, properties.dailyLimit(), now, ErrorCode.AI_DAILY_LIMIT_REACHED);
            reserve(reserved, ip, day, properties.dailyLimitPerIp(), now, ErrorCode.AI_IP_DAILY_LIMIT_REACHED);
            if (trial) {
                reserve(reserved, TRIAL_POOL, day, properties.trial().dailyPoolLimit(), now, ErrorCode.AI_TRIAL_POOL_EXHAUSTED);
            }
            reserve(reserved, SERVICE_POOL, day, properties.globalDailyLimit(), now, ErrorCode.AI_SERVICE_DAILY_LIMIT_REACHED);
            return List.copyOf(reserved);
        } catch (RuntimeException exception) {
            refund(reserved, day, now);
            throw exception;
        }
    }

    private void reserve(List<String> reserved, String key, LocalDate day, int limit, Instant now, ErrorCode error) {
        if (!store.incrementBelow(key, day, limit, now)) throw new ApiException(error);
        reserved.add(key);
    }

    private void refund(List<String> reserved, LocalDate day, Instant now) {
        // BOUNDARY: 같은 IP의 다른 요청이 올린 횟수나 거절된 counter는 내 요청의 환불 대상이 아니다.
        for (int i = reserved.size() - 1; i >= 0; i--) store.decrement(reserved.get(i), day, now);
    }

    public static String ipKey(String clientIp) {
        if (clientIp == null || clientIp.isBlank()) throw new IllegalArgumentException("trusted_client_ip_required");
        return "AI_IP:" + AuthService.hash(clientIp);
    }

    public Usage usage(Long userId) {
        Instant now = clock.instant();
        LocalDate day = serviceDate(now);
        int used = Math.min(store.used(userKey(userId), day), properties.dailyLimit());
        Instant resetsAt = ZonedDateTime.of(day.plusDays(1), LocalTime.MIDNIGHT, zone).toInstant();
        return new Usage(properties.dailyLimit(), used, properties.dailyLimit() - used, resetsAt);
    }

    public LocalDate serviceDate(Instant at) {
        return at.atZone(zone).toLocalDate();
    }

    public static String userKey(Long userId) {
        return "USER:" + userId;
    }

    /** 화면 표시용 오늘 사용 현황. resetsAt은 다음 한국 자정(UTC 시각). */
    public record Usage(int dailyLimit, int used, int remaining, Instant resetsAt) {
    }
}
