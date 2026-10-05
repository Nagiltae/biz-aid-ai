package com.bizaid;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.bizaid.common.error.ApiException;
import com.bizaid.common.maintenance.MaintenanceJob;
import com.bizaid.usage.application.AiUsageService;
import com.fasterxml.jackson.databind.JsonNode;
import java.sql.Timestamp;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;

/** 묶음5-1 공개 서비스 기능: 가입 필수 동의, 체험 계정(격리·수정 불가·만료 삭제), 하루 AI 사용 제한(경계·동시성·자정). */
@SpringBootTest
@AutoConfigureMockMvc
class PublicServiceTest extends ApiTestSupport {

    // 한국 날짜 2026-10-04의 마지막 순간과 다음 날 0시(UTC로는 15:00).
    private static final Instant KST_LAST_SECOND = Instant.parse("2026-10-04T14:59:59Z");
    private static final Instant KST_NEXT_MIDNIGHT = Instant.parse("2026-10-04T15:00:00Z");

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    AiUsageService usage;

    @Autowired
    MaintenanceJob maintenance;

    @BeforeEach
    void clearCounters() {
        jdbc.update("delete from ai_usage_counters");
    }

    @Test
    void signupRequiresBothConsentsAndRecordsVersionAndTime() throws Exception {
        String base = "{\"email\":\"consent@example.com\",\"password\":\"password123\",\"displayName\":\"동의\"";
        mvc.perform(post("/api/auth/signup").contentType(MediaType.APPLICATION_JSON).content(base + "}"))
                .andExpect(status().isBadRequest()).andExpect(jsonPath("$.error.code").value("validation_failed"));
        mvc.perform(post("/api/auth/signup").contentType(MediaType.APPLICATION_JSON)
                        .content(base + ",\"agreeTerms\":true,\"agreePrivacy\":false}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error.fieldErrors[0].field").value("agreePrivacy"));
        assertThat(jdbc.queryForObject("select count(*) from users where email = 'consent@example.com'", Integer.class)).isZero();

        long userId = read(mvc.perform(post("/api/auth/signup").contentType(MediaType.APPLICATION_JSON)
                        .content(base + ",\"agreeTerms\":true,\"agreePrivacy\":true}"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.user.trial").value(false))
                .andReturn().getResponse().getContentAsString()).get("user").get("id").asLong();
        List<String> rows = jdbc.queryForList("select concat(document_type, '@', document_version) from user_consents "
                + "where user_id = ? and agreed_at is not null order by document_type", String.class, userId);
        assertThat(rows).containsExactly("PRIVACY@2026-10-04.3", "TERMS@2026-10-04.3");
    }

    @Test
    void eachTrialIsANewIsolatedUserWithSyntheticCompany() throws Exception {
        mvc.perform(get("/api/auth/trial")).andExpect(status().isOk()).andExpect(jsonPath("$.enabled").value(true));
        JsonNode first = startTrial();
        JsonNode second = startTrial();
        assertThat(first.get("user").get("trial").asBoolean()).isTrue();
        assertThat(first.get("user").get("id").asLong()).isNotEqualTo(second.get("user").get("id").asLong());
        String tokenA = bearer(first);
        String tokenB = bearer(second);

        mvc.perform(get("/api/company").header(HttpHeaders.AUTHORIZATION, tokenA)).andExpect(status().isOk())
                .andExpect(jsonPath("$.region").value("경기도")).andExpect(jsonPath("$.companySize").value("소상공인"))
                .andExpect(jsonPath("$.businessStatus").value("영업중"));

        long conversationId = read(mvc.perform(post("/api/conversations").header(HttpHeaders.AUTHORIZATION, tokenA)
                        .contentType(MediaType.APPLICATION_JSON).content("{\"title\":\"체험 A 질문\"}"))
                .andExpect(status().isCreated()).andReturn().getResponse().getContentAsString()).get("id").asLong();
        // 다른 체험자는 목록에도 없고 직접 주소로도 볼 수 없다.
        mvc.perform(get("/api/conversations").header(HttpHeaders.AUTHORIZATION, tokenB))
                .andExpect(status().isOk()).andExpect(jsonPath("$.length()").value(0));
        mvc.perform(get("/api/conversations/" + conversationId + "/messages").header(HttpHeaders.AUTHORIZATION, tokenB))
                .andExpect(status().isNotFound());
        mvc.perform(get("/api/conversations").header(HttpHeaders.AUTHORIZATION, tokenA)).andExpect(jsonPath("$.length()").value(1));
        // 체험 계정도 동의 기록이 남는다(체험하기 버튼 아래 안내).
        assertThat(jdbc.queryForObject("select count(*) from user_consents where user_id = ?", Integer.class,
                first.get("user").get("id").asLong())).isEqualTo(2);
    }

    @Test
    void trialCannotEditCompanyChangePasswordOrWithdraw() throws Exception {
        String token = bearer(startTrial());
        String company = "{\"companyName\":\"바꾼 이름\",\"region\":\"서울특별시\"}";
        mvc.perform(put("/api/company").header(HttpHeaders.AUTHORIZATION, token).contentType(MediaType.APPLICATION_JSON).content(company))
                .andExpect(status().isForbidden()).andExpect(jsonPath("$.error.code").value("trial_account_restricted"));
        mvc.perform(post("/api/company").header(HttpHeaders.AUTHORIZATION, token).contentType(MediaType.APPLICATION_JSON).content(company))
                .andExpect(status().isForbidden()).andExpect(jsonPath("$.error.code").value("trial_account_restricted"));
        mvc.perform(put("/api/account/password").header(HttpHeaders.AUTHORIZATION, token).contentType(MediaType.APPLICATION_JSON)
                        .content("{\"currentPassword\":\"anything1\",\"newPassword\":\"password999\"}"))
                .andExpect(status().isForbidden()).andExpect(jsonPath("$.error.code").value("trial_account_restricted"));
        mvc.perform(post("/api/account/withdraw").header(HttpHeaders.AUTHORIZATION, token).contentType(MediaType.APPLICATION_JSON)
                        .content("{\"password\":\"anything1\"}"))
                .andExpect(status().isForbidden()).andExpect(jsonPath("$.error.code").value("trial_account_restricted"));
        mvc.perform(get("/api/company").header(HttpHeaders.AUTHORIZATION, token)).andExpect(jsonPath("$.companyName").value("체험용 가게"));
    }

    @Test
    void trialOlderThan24HoursIsDeletedWithItsDataByMaintenance() throws Exception {
        JsonNode old = startTrial();
        JsonNode fresh = startTrial();
        long oldId = old.get("user").get("id").asLong();
        long freshId = fresh.get("user").get("id").asLong();
        String oldToken = bearer(old);
        mvc.perform(post("/api/conversations").header(HttpHeaders.AUTHORIZATION, oldToken).contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"오래된 체험\"}")).andExpect(status().isCreated());
        usage.consume(oldId, true, "198.51.100.20", Instant.now());
        String member = signupWithCompany("member-keep@example.com");
        // 생성 시각만 25시간 전으로 옮긴다(24시간 경계를 넘긴 체험 계정).
        jdbc.update("update users set created_at = ? where id = ?", Timestamp.from(Instant.now().minus(Duration.ofHours(25))), oldId);

        MaintenanceJob.Summary summary = maintenance.daily();

        assertThat(summary.trialUsersDeleted()).isEqualTo(1);
        for (String table : new String[] {"users", "companies", "conversations", "user_consents", "refresh_tokens"}) {
            assertThat(count(table, table.equals("users") ? "id" : "user_id", oldId)).as(table).isZero();
        }
        assertThat(jdbc.queryForObject("select count(*) from ai_usage_counters where counter_key = ?", Integer.class,
                AiUsageService.userKey(oldId))).isZero();
        mvc.perform(get("/api/company").header(HttpHeaders.AUTHORIZATION, oldToken)).andExpect(status().isUnauthorized());
        // 24시간이 안 된 체험 계정과 일반 회원은 그대로다.
        assertThat(count("users", "id", freshId)).isEqualTo(1);
        mvc.perform(get("/api/company").header(HttpHeaders.AUTHORIZATION, member)).andExpect(status().isOk());
    }

    @Test
    void dailyLimitAllowsExactly10ThenFixed429AndResetsAtKoreanMidnight() {
        long userId = 900_001L;
        for (int i = 0; i < 10; i++) {
            usage.consume(userId, false, "198.51.100.20", KST_LAST_SECOND);
        }
        assertThatThrownBy(() -> usage.consume(userId, false, "198.51.100.20", KST_LAST_SECOND))
                .isInstanceOfSatisfying(ApiException.class, e -> assertThat(e.errorCode().code()).isEqualTo("ai_daily_limit_reached"));
        assertThat(used(userId, LocalDate.of(2026, 10, 4))).isEqualTo(10);
        // 한국 자정(UTC 15:00)이 지나면 새 날짜로 다시 센다.
        usage.consume(userId, false, "198.51.100.20", KST_NEXT_MIDNIGHT);
        assertThat(used(userId, LocalDate.of(2026, 10, 5))).isEqualTo(1);
    }

    @Test
    void concurrentRequestsNeverExceedTheLimit() throws Exception {
        long userId = 900_002L;
        ExecutorService pool = Executors.newFixedThreadPool(12);
        try {
            List<Callable<Boolean>> calls = new ArrayList<>();
            for (int i = 0; i < 60; i++) {
                calls.add(() -> {
                    try {
                        usage.consume(userId, false, "198.51.100.20", KST_LAST_SECOND);
                        return true;
                    } catch (ApiException exception) {
                        return false;
                    }
                });
            }
            int allowed = 0;
            for (Future<Boolean> result : pool.invokeAll(calls)) {
                allowed += result.get() ? 1 : 0;
            }
            assertThat(allowed).isEqualTo(10);
            assertThat(used(userId, LocalDate.of(2026, 10, 4))).isEqualTo(10);
        } finally {
            pool.shutdownNow();
        }
    }

    @Test
    void apiReturns429WhenUsedUpAndRefundsWhenAiGivesNoResult() throws Exception {
        String token = signupWithCompany("usage@example.com");
        long userId = userId("usage@example.com");
        mvc.perform(get("/api/ai/usage").header(HttpHeaders.AUTHORIZATION, token)).andExpect(status().isOk())
                .andExpect(jsonPath("$.dailyLimit").value(10)).andExpect(jsonPath("$.remaining").value(10));
        // 테스트 AI 주소는 연결되지 않는다(503). 결과를 못 받은 요청은 횟수를 되돌린다.
        mvc.perform(post("/api/ai/query").header(HttpHeaders.AUTHORIZATION, token).contentType(MediaType.APPLICATION_JSON)
                .content("{\"query\":\"금융 지원사업\"}")).andExpect(status().isServiceUnavailable());
        mvc.perform(get("/api/ai/usage").header(HttpHeaders.AUTHORIZATION, token)).andExpect(jsonPath("$.used").value(0));

        // 위 요청이 0으로 되돌린 오늘 행을 한도까지 쓴 상태로 바꾼다.
        assertThat(jdbc.update("update ai_usage_counters set used_count = 10 where counter_key = ?", AiUsageService.userKey(userId)))
                .isEqualTo(1);
        for (String path : new String[] {"/api/ai/query", "/api/ai/workflows"}) {
            mvc.perform(post(path).header(HttpHeaders.AUTHORIZATION, token).contentType(MediaType.APPLICATION_JSON)
                            .content("{\"query\":\"금융 지원사업\"}"))
                    .andExpect(status().isTooManyRequests()).andExpect(jsonPath("$.error.code").value("ai_daily_limit_reached"))
                    .andExpect(jsonPath("$.error.message").value("오늘 사용 가능한 횟수를 모두 사용했어요. 내일 다시 이용해 주세요."));
        }
        mvc.perform(get("/api/ai/usage").header(HttpHeaders.AUTHORIZATION, token)).andExpect(jsonPath("$.remaining").value(0));
    }

    @Test
    void trialPoolCapStopsAllTrialsWithoutChargingTheUser() throws Exception {
        JsonNode trial = startTrial();
        long userId = trial.get("user").get("id").asLong();
        LocalDate today = usage.serviceDate(Instant.now());
        jdbc.update("insert into ai_usage_counters (counter_key, usage_date, used_count, updated_at) values (?, ?, 200, ?)",
                AiUsageService.TRIAL_POOL, java.sql.Date.valueOf(today), Timestamp.from(Instant.now()));
        mvc.perform(post("/api/ai/query").header(HttpHeaders.AUTHORIZATION, bearer(trial)).contentType(MediaType.APPLICATION_JSON)
                        .content("{\"query\":\"금융 지원사업\"}"))
                .andExpect(status().isTooManyRequests()).andExpect(jsonPath("$.error.code").value("ai_trial_pool_exhausted"));
        assertThat(used(userId, today)).isZero();
    }

    private JsonNode startTrial() throws Exception {
        return read(mvc.perform(post("/api/auth/trial")).andExpect(status().isOk()).andReturn().getResponse().getContentAsString());
    }

    private static String bearer(JsonNode tokens) {
        return "Bearer " + tokens.get("accessToken").asText();
    }

    private int used(long userId, LocalDate day) {
        List<Integer> rows = jdbc.queryForList("select used_count from ai_usage_counters where counter_key = ? and usage_date = ?",
                Integer.class, AiUsageService.userKey(userId), java.sql.Date.valueOf(day));
        return rows.isEmpty() ? 0 : rows.get(0);
    }

    private long userId(String email) {
        return jdbc.queryForObject("select id from users where email = ?", Long.class, email);
    }

    private int count(String table, String column, long id) {
        return jdbc.queryForObject("select count(*) from " + table + " where " + column + " = ?", Integer.class, id);
    }
}
