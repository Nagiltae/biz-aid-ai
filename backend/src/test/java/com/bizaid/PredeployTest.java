package com.bizaid;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.bizaid.auth.application.SignupThrottleService;
import com.bizaid.common.error.ApiException;
import com.bizaid.usage.application.AiUsageService;
import com.bizaid.usage.infrastructure.UsageCounterStore;
import java.sql.Date;
import java.sql.Timestamp;
import java.time.Instant;
import java.time.LocalDate;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;

/** 운영 상한과 실제 접속 IP의 남용 제한. H2만 사용하며 기존 dev 데이터에는 쓰지 않는다. */
@SpringBootTest(properties = {"bizaid.usage.signup-per-ip-per-day=5", "bizaid.usage.trial.max-creates-per-ip-per-day=2"})
@AutoConfigureMockMvc
class PredeployTest extends ApiTestSupport {
    @Autowired JdbcTemplate jdbc;
    @Autowired AiUsageService usage;
    @Autowired UsageCounterStore store;
    @Autowired SignupThrottleService signupThrottle;

    @BeforeEach
    void clearCounters() {
        jdbc.update("delete from ai_usage_counters");
    }

    @Test
    void globalDailyLimitRejectsAndRollsBackAllEarlierReservations() {
        Instant now = Instant.now();
        LocalDate day = usage.serviceDate(now);
        jdbc.update("insert into ai_usage_counters (counter_key, usage_date, used_count, updated_at) values (?, ?, 300, ?)",
                AiUsageService.SERVICE_POOL, Date.valueOf(day), Timestamp.from(now));
        assertThatThrownBy(() -> usage.consume(9999L, true, "198.51.100.20", now)).isInstanceOfSatisfying(ApiException.class,
                error -> assertThat(error.errorCode().code()).isEqualTo("ai_service_daily_limit_reached"));
        assertThat(store.used(AiUsageService.userKey(9999L), day)).isZero();
        assertThat(store.used(AiUsageService.TRIAL_POOL, day)).isZero();
        assertThat(store.used(AiUsageService.SERVICE_POOL, day)).isEqualTo(300);
        assertThat(store.used(AiUsageService.ipKey("198.51.100.20"), day)).isZero();
    }

    @Test
    void unexpectedAiFailureRefundsBothGlobalAndUserCounters() {
        var user = new com.bizaid.auth.domain.AuthUser(9998L, "fixture@example.com", true);
        assertThatThrownBy(() -> usage.run(user, "198.51.100.20", () -> { throw new IllegalStateException("fixture"); }))
                .isInstanceOf(IllegalStateException.class);
        LocalDate day = usage.serviceDate(Instant.now());
        assertThat(store.used(AiUsageService.userKey(9998L), day)).isZero();
        assertThat(store.used(AiUsageService.SERVICE_POOL, day)).isZero();
        assertThat(store.used(AiUsageService.ipKey("198.51.100.20"), day)).isZero();
        assertThat(store.used(AiUsageService.TRIAL_POOL, day)).isZero();
    }

    @Test
    void differentAccountsShareThirtyAndTheNextRequestGetsIpMessage() throws Exception {
        Instant now = Instant.now();
        String ip = "198.51.100.40";
        for (int i = 0; i < 30; i++) usage.consume(9100L + i / 10, false, ip, now);
        String token = signupWithCompany("ip-limit@example.com");
        mvc.perform(post("/api/ai/query").header(org.springframework.http.HttpHeaders.AUTHORIZATION, token)
                .with(request -> { request.setRemoteAddr(ip); return request; }).header("X-Forwarded-For", "203.0.113.9")
                .contentType(MediaType.APPLICATION_JSON).content("{\"query\":\"금융 지원사업\"}"))
                .andExpect(status().isTooManyRequests()).andExpect(jsonPath("$.error.code").value("ai_ip_daily_limit_reached"))
                .andExpect(jsonPath("$.error.message").value("이 네트워크에서 오늘 사용할 수 있는 AI 횟수를 모두 사용했어요. 내일 다시 이용해 주세요."));
        LocalDate day = usage.serviceDate(now);
        assertThat(store.used(AiUsageService.ipKey(ip), day)).isEqualTo(30);
        assertThat(store.used(AiUsageService.SERVICE_POOL, day)).isEqualTo(30);
        assertThat(jdbc.queryForList("select counter_key from ai_usage_counters where counter_key like 'AI_IP:%'", String.class))
                .allMatch(key -> key.matches("AI_IP:[0-9a-f]{64}"));
        long id = jdbc.queryForObject("select id from users where email = 'ip-limit@example.com'", Long.class);
        assertThat(store.used(AiUsageService.userKey(id), day)).isZero();
    }

    @Test
    void trialPoolRejectionRestoresAccountAndIpReservations() {
        Instant now = Instant.now();
        LocalDate day = usage.serviceDate(now);
        jdbc.update("insert into ai_usage_counters (counter_key, usage_date, used_count, updated_at) values (?, ?, 200, ?)",
                AiUsageService.TRIAL_POOL, Date.valueOf(day), Timestamp.from(now));
        assertThatThrownBy(() -> usage.consume(9200L, true, "198.51.100.41", now)).isInstanceOf(ApiException.class);
        assertThat(store.used(AiUsageService.userKey(9200L), day)).isZero();
        assertThat(store.used(AiUsageService.ipKey("198.51.100.41"), day)).isZero();
        assertThat(store.used(AiUsageService.TRIAL_POOL, day)).isEqualTo(200);
        assertThat(store.used(AiUsageService.SERVICE_POOL, day)).isZero();
    }

    @Test
    void concurrentAccountsNeverExceedSharedIpOrIndividualLimits() throws Exception {
        Instant now = Instant.now();
        LocalDate day = usage.serviceDate(now);
        String ip = "198.51.100.42";
        var pool = java.util.concurrent.Executors.newFixedThreadPool(12);
        try {
            java.util.List<java.util.concurrent.Callable<Boolean>> calls = new java.util.ArrayList<>();
            for (int i = 0; i < 60; i++) {
                long id = 9300L + i % 6;
                calls.add(() -> {
                    try { usage.consume(id, true, ip, now); return true; }
                    catch (ApiException exception) { return false; }
                });
            }
            int allowed = 0;
            for (var result : pool.invokeAll(calls)) if (result.get()) allowed++;
            assertThat(allowed).isEqualTo(30);
            assertThat(store.used(AiUsageService.ipKey(ip), day)).isEqualTo(30);
            assertThat(store.used(AiUsageService.SERVICE_POOL, day)).isEqualTo(30);
            assertThat(store.used(AiUsageService.TRIAL_POOL, day)).isEqualTo(30);
            int sum = 0;
            for (long id = 9300L; id < 9306L; id++) {
                int count = store.used(AiUsageService.userKey(id), day);
                assertThat(count).isBetween(0, 10);
                sum += count;
            }
            assertThat(sum).isEqualTo(30);
        } finally { pool.shutdownNow(); }
    }

    @Test
    void sevenDayOldIpHashesAreDeletedAndRecentCountersRemain() {
        Instant now = Instant.now();
        LocalDate day = usage.serviceDate(now);
        String key = AiUsageService.ipKey("198.51.100.43");
        store.incrementBelow(key, day.minusDays(7), 30, now);
        store.incrementBelow(key, day.minusDays(6), 30, now);
        assertThat(store.deleteBefore(day.minusDays(7))).isEqualTo(1);
        assertThat(store.used(key, day.minusDays(7))).isZero();
        assertThat(store.used(key, day.minusDays(6))).isEqualTo(1);
    }

    @Test
    void signupIpAllowsFiveAndDoesNotStoreRawIp() {
        for (int i = 0; i < 5; i++) signupThrottle.reserve("198.51.100.10");
        assertThatThrownBy(() -> signupThrottle.reserve("198.51.100.10"))
                .isInstanceOfSatisfying(ApiException.class,
                        error -> assertThat(error.errorCode().code()).isEqualTo("auth_signup_limited"));
        signupThrottle.reserve("198.51.100.11");
        assertThat(jdbc.queryForList("select counter_key from ai_usage_counters", String.class))
                .allMatch(key -> key.matches("SIGNUP_IP:[0-9a-f]{64}"));
    }

    @Test
    void forgedForwardedHeaderCannotResetTrialOrSignupLimit() throws Exception {
        for (int i = 0; i < 2; i++) {
            mvc.perform(post("/api/auth/trial").with(request -> { request.setRemoteAddr("198.51.100.12"); return request; })
                    .header("X-Forwarded-For", "203.0.113." + i)).andExpect(status().isOk());
        }
        mvc.perform(post("/api/auth/trial").with(request -> { request.setRemoteAddr("198.51.100.12"); return request; })
                .header("X-Forwarded-For", "203.0.113.100")).andExpect(status().isTooManyRequests());
        for (int i = 0; i < 5; i++) signupThrottle.reserve("198.51.100.13");
        mvc.perform(post("/api/auth/signup").with(request -> { request.setRemoteAddr("198.51.100.13"); return request; })
                .header("X-Forwarded-For", "203.0.113.99").contentType(MediaType.APPLICATION_JSON)
                .content("{\"email\":\"limited@example.com\",\"password\":\"password123\",\"displayName\":\"시험\",\"agreeTerms\":true,\"agreePrivacy\":true}"))
                .andExpect(status().isTooManyRequests()).andExpect(jsonPath("$.error.code").value("auth_signup_limited"));
    }

    @Test
    void healthDoesNotExposeDependencyDetails() throws Exception {
        mvc.perform(get("/api/health")).andExpect(status().isOk()).andExpect(jsonPath("$.status").value("ok"))
                .andExpect(jsonPath("$.length()").value(1));
    }
}
