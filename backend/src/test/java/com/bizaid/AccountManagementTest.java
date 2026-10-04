package com.bizaid;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.bizaid.ai.domain.AiWorkflow;
import com.bizaid.ai.infrastructure.AiWorkflowRepository;
import com.bizaid.auth.domain.LoginThrottle;
import com.bizaid.common.maintenance.MaintenanceJob;
import jakarta.servlet.http.Cookie;
import java.sql.Timestamp;
import java.time.Duration;
import java.time.Instant;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

/** 묶음3 서비스 관리: 회원 탈퇴·대화 삭제·로그인 시도 제한·비밀번호 변경·정리 스케줄러. */
@SpringBootTest
@AutoConfigureMockMvc
class AccountManagementTest extends ApiTestSupport {

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    AiWorkflowRepository workflows;

    @Autowired
    MaintenanceJob maintenance;

    @BeforeEach
    void clearThrottles() {
        // 다른 테스트의 로그인 실패(같은 테스트 IP)가 이번 검사에 섞이지 않게 제한 상태를 비운다.
        jdbc.update("delete from login_throttles");
    }

    @Test
    void withdrawalDeletesServiceDataAnonymizesLogsAndInvalidatesTokens() throws Exception {
        MvcResult signup = mvc.perform(post("/api/auth/signup").contentType(MediaType.APPLICATION_JSON)
                        .content("{\"email\":\"leave@example.com\",\"password\":\"password123\",\"displayName\":\"탈퇴자\",\"agreeTerms\":true,\"agreePrivacy\":true}"))
                .andExpect(status().isOk()).andReturn();
        String token = "Bearer " + read(signup.getResponse().getContentAsString()).get("accessToken").asText();
        Cookie refresh = signup.getResponse().getCookie("bizaid_refresh");
        long userId = read(signup.getResponse().getContentAsString()).get("user").get("id").asLong();
        mvc.perform(post("/api/company").header(HttpHeaders.AUTHORIZATION, token).contentType(MediaType.APPLICATION_JSON)
                .content("{\"companyName\":\"탈퇴상사\"}")).andExpect(status().isCreated());
        long conversationId = read(mvc.perform(post("/api/conversations").header(HttpHeaders.AUTHORIZATION, token)
                        .contentType(MediaType.APPLICATION_JSON).content("{\"title\":\"질문\"}"))
                .andExpect(status().isCreated()).andReturn().getResponse().getContentAsString()).get("id").asLong();
        mvc.perform(post("/api/conversations/" + conversationId + "/messages").header(HttpHeaders.AUTHORIZATION, token)
                .contentType(MediaType.APPLICATION_JSON).content("{\"content\":\"금융 지원사업\"}")).andExpect(status().isCreated());
        workflows.saveAndFlush(new AiWorkflow(userId, "{\"status\":\"COMPLETED\"}", "COMPLETED", "DONE", Instant.now()));

        // 비밀번호 재확인이 틀리면 아무것도 지우지 않는다(401이 아닌 400이라 화면이 토큰 재발급을 시도하지 않는다).
        mvc.perform(post("/api/account/withdraw").header(HttpHeaders.AUTHORIZATION, token).contentType(MediaType.APPLICATION_JSON)
                        .content("{\"password\":\"wrong-password\"}"))
                .andExpect(status().isBadRequest()).andExpect(jsonPath("$.error.code").value("auth_password_mismatch"));
        assertThat(count("users", "id", userId)).isEqualTo(1);

        MvcResult withdrawn = mvc.perform(post("/api/account/withdraw").header(HttpHeaders.AUTHORIZATION, token)
                        .contentType(MediaType.APPLICATION_JSON).content("{\"password\":\"password123\"}"))
                .andExpect(status().isNoContent()).andReturn();
        assertThat(withdrawn.getResponse().getHeader(HttpHeaders.SET_COOKIE)).contains("Max-Age=0");
        for (String table : new String[] {"users", "companies", "conversations", "ai_workflows", "refresh_tokens"}) {
            assertThat(count(table, table.equals("users") ? "id" : "user_id", userId)).as(table).isZero();
        }
        assertThat(jdbc.queryForObject("select count(*) from messages where conversation_id = ?", Integer.class, conversationId)).isZero();
        // 활동 기록은 남지만 그 사람을 가리키는 값은 없다.
        assertThat(count("activity_logs", "user_id", userId)).isZero();
        assertThat(jdbc.queryForObject("select count(*) from activity_logs where action = 'ACCOUNT_DELETE' and user_id is null",
                Integer.class)).isPositive();
        // 탈퇴 전 Access Token·Refresh Token은 즉시 쓸 수 없다.
        mvc.perform(get("/api/auth/me").header(HttpHeaders.AUTHORIZATION, token)).andExpect(status().isUnauthorized());
        mvc.perform(post("/api/auth/refresh").cookie(refresh)).andExpect(status().isUnauthorized());
        mvc.perform(post("/api/auth/login").contentType(MediaType.APPLICATION_JSON)
                .content("{\"email\":\"leave@example.com\",\"password\":\"password123\"}")).andExpect(status().isUnauthorized());
    }

    @Test
    void recentWorkflowsAreListedForTheOwnerOnly() throws Exception {
        MvcResult signup = mvc.perform(post("/api/auth/signup").contentType(MediaType.APPLICATION_JSON)
                        .content("{\"email\":\"history@example.com\",\"password\":\"password123\",\"displayName\":\"기록\",\"agreeTerms\":true,\"agreePrivacy\":true}"))
                .andExpect(status().isOk()).andReturn();
        String token = "Bearer " + read(signup.getResponse().getContentAsString()).get("accessToken").asText();
        long userId = read(signup.getResponse().getContentAsString()).get("user").get("id").asLong();
        workflows.saveAndFlush(new AiWorkflow(userId, "{\"query\":\"금융 지원사업\",\"status\":\"COMPLETED\","
                + "\"final_result\":{\"counts\":{\"recommended\":2}}}", "COMPLETED", "DONE", Instant.now()));
        mvc.perform(get("/api/ai/workflows").header(HttpHeaders.AUTHORIZATION, token))
                .andExpect(status().isOk()).andExpect(jsonPath("$.length()").value(1))
                .andExpect(jsonPath("$[0].query").value("금융 지원사업")).andExpect(jsonPath("$[0].recommendedCount").value(2));
        String other = signup("history-other@example.com");
        mvc.perform(get("/api/ai/workflows").header(HttpHeaders.AUTHORIZATION, other))
                .andExpect(status().isOk()).andExpect(jsonPath("$.length()").value(0));
    }

    @Test
    void conversationDeleteIsOwnerOnly() throws Exception {
        String owner = signupWithCompany("owner-delete@example.com");
        String other = signupWithCompany("other-delete@example.com");
        long id = read(mvc.perform(post("/api/conversations").header(HttpHeaders.AUTHORIZATION, owner)
                        .contentType(MediaType.APPLICATION_JSON).content("{\"title\":\"지울 대화\"}"))
                .andExpect(status().isCreated()).andReturn().getResponse().getContentAsString()).get("id").asLong();
        mvc.perform(post("/api/conversations/" + id + "/messages").header(HttpHeaders.AUTHORIZATION, owner)
                .contentType(MediaType.APPLICATION_JSON).content("{\"content\":\"메시지\"}")).andExpect(status().isCreated());
        // 남의 대화는 존재 여부를 알리지 않는 같은 404다.
        mvc.perform(delete("/api/conversations/" + id).header(HttpHeaders.AUTHORIZATION, other))
                .andExpect(status().isNotFound()).andExpect(jsonPath("$.error.code").value("conversation_not_found"));
        mvc.perform(delete("/api/conversations/" + id).header(HttpHeaders.AUTHORIZATION, owner)).andExpect(status().isNoContent());
        assertThat(jdbc.queryForObject("select count(*) from messages where conversation_id = ?", Integer.class, id)).isZero();
        mvc.perform(get("/api/conversations/" + id + "/messages").header(HttpHeaders.AUTHORIZATION, owner))
                .andExpect(status().isNotFound());
        mvc.perform(delete("/api/conversations/" + id).header(HttpHeaders.AUTHORIZATION, owner)).andExpect(status().isNotFound());
    }

    @Test
    void accountIsLockedAfterFiveFailuresAndSuccessResetsTheCount() throws Exception {
        signup("lock@example.com");
        // 4번 틀리고 1번 맞으면 계정 횟수가 0으로 돌아간다.
        for (int index = 0; index < 4; index++) {
            login("lock@example.com", "wrong-password", "10.1.0.1").andExpect(status().isUnauthorized());
        }
        login("lock@example.com", "password123", "10.1.0.1").andExpect(status().isOk());
        for (int index = 0; index < 4; index++) {
            login("lock@example.com", "wrong-password", "10.1.0.2").andExpect(status().isUnauthorized());
        }
        login("lock@example.com", "password123", "10.1.0.2").andExpect(status().isOk());
        // 연속 5번째 실패에서 잠기고, 잠긴 동안은 맞는 비밀번호도 받지 않는다(다른 IP에서도).
        for (int index = 0; index < 5; index++) {
            login("lock@example.com", "wrong-password", "10.1.0.3").andExpect(status().isUnauthorized());
        }
        login("lock@example.com", "password123", "10.1.0.4")
                .andExpect(status().isTooManyRequests()).andExpect(jsonPath("$.error.code").value("auth_login_locked"))
                .andExpect(jsonPath("$.error.message").value("로그인 실패가 반복되어 잠시 로그인할 수 없습니다. 10분 뒤에 다시 시도해 주세요."));
        // 이메일·IP 원문은 저장하지 않는다.
        assertThat(jdbc.queryForObject("select count(*) from login_throttles where throttle_key like '%@%' or throttle_key like '10.%'",
                Integer.class)).isZero();
    }

    @Test
    void sameIpIsLockedAcrossAccounts() throws Exception {
        for (int index = 0; index < 5; index++) {
            login("nobody" + index + "@example.com", "wrong-password", "10.2.0.9").andExpect(status().isUnauthorized());
        }
        signup("ip-victim@example.com");
        login("ip-victim@example.com", "password123", "10.2.0.9").andExpect(status().isTooManyRequests());
        login("ip-victim@example.com", "password123", "10.2.0.10").andExpect(status().isOk());
    }

    @Test
    void lockEndsAfterTheLockDuration() {
        LoginThrottle throttle = new LoginThrottle("k", "ACCOUNT", Instant.parse("2026-10-04T00:00:00Z"));
        Instant start = Instant.parse("2026-10-04T00:00:00Z");
        for (int index = 0; index < 5; index++) {
            throttle.recordFailure(start, 5, Duration.ofMinutes(10));
        }
        assertThat(throttle.isLocked(start.plus(Duration.ofMinutes(9)))).isTrue();
        assertThat(throttle.isLocked(start.plus(Duration.ofMinutes(10)))).isFalse();
        // 잠금이 끝난 뒤에는 다시 5번을 센다.
        throttle.recordFailure(start.plus(Duration.ofMinutes(11)), 5, Duration.ofMinutes(10));
        assertThat(throttle.isLocked(start.plus(Duration.ofMinutes(11)))).isFalse();
    }

    @Test
    void passwordChangeRequiresCurrentPasswordAndRevokesOtherSessions() throws Exception {
        MvcResult signup = mvc.perform(post("/api/auth/signup").contentType(MediaType.APPLICATION_JSON)
                        .content("{\"email\":\"change@example.com\",\"password\":\"password123\",\"displayName\":\"변경\",\"agreeTerms\":true,\"agreePrivacy\":true}"))
                .andExpect(status().isOk()).andReturn();
        String token = "Bearer " + read(signup.getResponse().getContentAsString()).get("accessToken").asText();
        Cookie oldRefresh = signup.getResponse().getCookie("bizaid_refresh");
        mvc.perform(put("/api/account/password").header(HttpHeaders.AUTHORIZATION, token).contentType(MediaType.APPLICATION_JSON)
                        .content("{\"currentPassword\":\"wrong-password\",\"newPassword\":\"newpassword456\"}"))
                .andExpect(status().isBadRequest()).andExpect(jsonPath("$.error.code").value("auth_password_mismatch"));
        mvc.perform(put("/api/account/password").header(HttpHeaders.AUTHORIZATION, token).contentType(MediaType.APPLICATION_JSON)
                        .content("{\"currentPassword\":\"password123\",\"newPassword\":\"short\"}"))
                .andExpect(status().isBadRequest()).andExpect(jsonPath("$.error.fieldErrors[0].field").value("newPassword"));
        mvc.perform(put("/api/account/password").header(HttpHeaders.AUTHORIZATION, token).contentType(MediaType.APPLICATION_JSON)
                        .content("{\"currentPassword\":\"password123\",\"newPassword\":\"newpassword456\"}"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.accessToken").isNotEmpty());
        // 다른 기기(이전 Refresh Token)는 끊긴다. 새 비밀번호로만 로그인된다.
        mvc.perform(post("/api/auth/refresh").cookie(oldRefresh)).andExpect(status().isUnauthorized());
        login("change@example.com", "password123", "10.3.0.1").andExpect(status().isUnauthorized());
        login("change@example.com", "newpassword456", "10.3.0.1").andExpect(status().isOk());
    }

    @Test
    void maintenanceDeletesOldTokensExpiresIdleWorkflowsAndKeepsActiveOnes() throws Exception {
        long userId = read(mvc.perform(post("/api/auth/signup").contentType(MediaType.APPLICATION_JSON)
                        .content("{\"email\":\"maint@example.com\",\"password\":\"password123\",\"displayName\":\"정리\",\"agreeTerms\":true,\"agreePrivacy\":true}"))
                .andReturn().getResponse().getContentAsString()).get("user").get("id").asLong();
        Instant old = Instant.now().minus(Duration.ofDays(120));
        jdbc.update("insert into refresh_tokens (user_id, token_hash, expires_at, revoked_at, created_at) values (?, ?, ?, ?, ?)",
                userId, "f".repeat(64), Timestamp.from(old), Timestamp.from(old), Timestamp.from(old));
        long idle = workflows.saveAndFlush(new AiWorkflow(userId, "{\"status\":\"WAITING_FOR_USER\",\"pending\":[]}",
                "WAITING_FOR_USER", "AWAIT_ANSWERS", Instant.now())).getId();
        long finished = workflows.saveAndFlush(new AiWorkflow(userId, "{\"status\":\"COMPLETED\"}", "COMPLETED", "DONE", Instant.now())).getId();
        long recent = workflows.saveAndFlush(new AiWorkflow(userId, "{\"status\":\"IN_PROGRESS\"}", "IN_PROGRESS", "EVALUATE_PROGRAM",
                Instant.now())).getId();
        jdbc.update("update ai_workflows set updated_at = ? where id in (?, ?)", Timestamp.from(old), idle, finished);
        jdbc.update("update ai_workflows set step_started_at = ? where id = ?", Timestamp.from(Instant.now().minus(Duration.ofMinutes(30))), recent);

        MaintenanceJob.Summary summary = maintenance.daily();

        assertThat(summary.refreshTokensDeleted()).isPositive();
        assertThat(jdbc.queryForObject("select count(*) from refresh_tokens where token_hash = ?", Integer.class, "f".repeat(64))).isZero();
        // 오래 방치된 진행 중 흐름은 지우지 않고 FAILED(workflow_expired)로 만료한다. State JSON도 같은 상태다.
        assertThat(jdbc.queryForObject("select status from ai_workflows where id = ?", String.class, idle)).isEqualTo("FAILED");
        assertThat(read(jdbc.queryForObject("select state_json from ai_workflows where id = ?", String.class, idle))
                .get("failure_code").asText()).isEqualTo("workflow_expired");
        // 보관 기간이 지난 끝난 흐름만 지운다. 최근 진행 중 흐름은 남고 오래된 점유만 풀린다.
        assertThat(count("ai_workflows", "id", finished)).isZero();
        assertThat(jdbc.queryForObject("select status from ai_workflows where id = ?", String.class, recent)).isEqualTo("IN_PROGRESS");
        assertThat(jdbc.queryForObject("select step_started_at from ai_workflows where id = ?", Timestamp.class, recent)).isNull();
    }

    private org.springframework.test.web.servlet.ResultActions login(String email, String password, String ip) throws Exception {
        MockHttpServletRequestBuilder request = post("/api/auth/login").contentType(MediaType.APPLICATION_JSON)
                .content("{\"email\":\"" + email + "\",\"password\":\"" + password + "\"}")
                .with(servlet -> {
                    servlet.setRemoteAddr(ip);
                    return servlet;
                });
        return mvc.perform(request);
    }

    private int count(String table, String column, long value) {
        return jdbc.queryForObject("select count(*) from " + table + " where " + column + " = ?", Integer.class, value);
    }
}
