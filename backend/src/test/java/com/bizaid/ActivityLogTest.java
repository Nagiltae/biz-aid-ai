package com.bizaid;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import jakarta.servlet.http.Cookie;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MvcResult;

/** 활동 기록이 성공·실패를 남기고, 실패로 본 트랜잭션이 되돌려져도 기록은 남으며, 비밀값을 저장하지 않는지 확인한다. */
@SpringBootTest
@AutoConfigureMockMvc
class ActivityLogTest extends ApiTestSupport {

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void authAndCompanyActivitiesAreRecordedWithoutSecrets() throws Exception {
        String token = signup("activity@example.com");
        Long userId = jdbc.queryForObject("SELECT id FROM users WHERE email = 'activity@example.com'", Long.class);
        mvc.perform(post("/api/auth/login").contentType(MediaType.APPLICATION_JSON)
                .content("{\"email\":\"activity@example.com\",\"password\":\"wrong-password-9\"}")).andExpect(status().isUnauthorized());
        MvcResult login = mvc.perform(post("/api/auth/login").contentType(MediaType.APPLICATION_JSON)
                .content("{\"email\":\"activity@example.com\",\"password\":\"password123\"}")).andExpect(status().isOk()).andReturn();
        Cookie refresh = login.getResponse().getCookie("bizaid_refresh");
        mvc.perform(post("/api/company").header(HttpHeaders.AUTHORIZATION, token).contentType(MediaType.APPLICATION_JSON)
                .content("{\"companyName\":\"기록상사\"}")).andExpect(status().isCreated());
        mvc.perform(post("/api/auth/logout").cookie(refresh)).andExpect(status().isNoContent());

        List<Map<String, Object>> rows = jdbc.queryForList(
                "SELECT action, success, error_code, metadata_json FROM activity_logs WHERE user_id = ? ORDER BY id", userId);
        assertThat(rows).extracting(row -> row.get("action") + ":" + row.get("success")).containsExactly(
                "SIGNUP:true", "LOGIN:false", "LOGIN:true", "COMPANY_CREATE:true", "LOGOUT:true");
        // 로그인 실패는 서비스 트랜잭션이 되돌려져도 별도 트랜잭션으로 남는다.
        assertThat(rows.get(1).get("error_code")).isEqualTo("auth_invalid_credentials");
        assertThat(String.valueOf(rows.get(1).get("metadata_json"))).contains("wrong_password");
        // BOUNDARY: 비밀번호·Access Token·Refresh Token 원문은 어떤 column에도 없다.
        String everything = jdbc.queryForList("SELECT * FROM activity_logs").toString();
        assertThat(everything).doesNotContain("password123", "wrong-password-9", token.substring("Bearer ".length()),
                refresh.getValue());
    }
}
