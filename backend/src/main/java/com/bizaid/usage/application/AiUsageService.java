package com.bizaid.usage.application;

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
import java.util.function.Supplier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

/**
 * 하루 AI 사용 제한(2026-10-04 묶음5-1 사용자 결정).
 * 사용자별 하루 dailyLimit회, 한국 시간 자정에 새로 센다. AI 검색 질문·맞춤 추천 시작·단일 자격 판정 1회를 1로 센다.
 * 추천의 다음 단계 진행·부족 정보 답변은 세지 않는다. 체험 계정은 체험 전체 합산 상한(TRIAL_POOL)도 함께 쓴다.
 *
 * <p>BOUNDARY: 트랜잭션을 두지 않는다. 각 증감은 DB 한 문장으로 바로 commit되고, 체험 합산에서 막히면 이미 올린 사용자 횟수를 되돌린다.
 * <p>EXCEPTION: AI가 결과를 주지 못한 요청(ApiException: 기업정보 없음·AI 시간 초과 등)은 횟수를 되돌린다.
 */
@Service
public class AiUsageService {

    public static final String TRIAL_POOL = "TRIAL_POOL";

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

    /** 횟수를 하나 쓰고 AI 기능을 실행한다. 실행이 ApiException으로 끝나면 쓴 횟수를 되돌린다. */
    public <T> T run(AuthUser user, Supplier<T> action) {
        Instant now = clock.instant();
        LocalDate day = serviceDate(now);
        consume(user.id(), user.trial(), now);
        try {
            return action.get();
        } catch (ApiException exception) {
            refund(user.id(), user.trial(), day, clock.instant());
            throw exception;
        }
    }

    /** 사용자 횟수 → (체험이면) 체험 합산 순서로 하나씩 쓴다. 어느 쪽이든 상한이면 429 고정 코드. */
    public void consume(Long userId, boolean trial, Instant now) {
        LocalDate day = serviceDate(now);
        if (!store.incrementBelow(userKey(userId), day, properties.dailyLimit(), now)) {
            throw new ApiException(ErrorCode.AI_DAILY_LIMIT_REACHED);
        }
        if (trial && !store.incrementBelow(TRIAL_POOL, day, properties.trial().dailyPoolLimit(), now)) {
            store.decrement(userKey(userId), day, now);
            throw new ApiException(ErrorCode.AI_TRIAL_POOL_EXHAUSTED);
        }
    }

    void refund(Long userId, boolean trial, LocalDate day, Instant now) {
        store.decrement(userKey(userId), day, now);
        if (trial) {
            store.decrement(TRIAL_POOL, day, now);
        }
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
