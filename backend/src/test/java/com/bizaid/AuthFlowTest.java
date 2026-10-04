package com.bizaid;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import jakarta.servlet.http.Cookie;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class AuthFlowTest extends ApiTestSupport {

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void loginRefreshRotationAndLogout() throws Exception {
        mvc.perform(post("/api/auth/signup").contentType(MediaType.APPLICATION_JSON)
                        .content("{\"email\":\"Owner@Example.com\",\"password\":\"password123\",\"displayName\":\"대표\",\"agreeTerms\":true,\"agreePrivacy\":true}"))
                .andExpect(status().isOk());
        mvc.perform(post("/api/auth/login").contentType(MediaType.APPLICATION_JSON)
                        .content("{\"email\":\"owner@example.com\",\"password\":\"wrong-password\"}"))
                .andExpect(status().isUnauthorized()).andExpect(jsonPath("$.error.code").value("auth_invalid_credentials"));

        MvcResult login = mvc.perform(post("/api/auth/login").contentType(MediaType.APPLICATION_JSON)
                        .content("{\"email\":\"owner@example.com\",\"password\":\"password123\"}"))
                .andExpect(status().isOk()).andReturn();
        String setCookie = login.getResponse().getHeader(HttpHeaders.SET_COOKIE);
        // Refresh Token은 HttpOnly Cookie로만 내려가고 응답 본문에는 없다.
        assertThat(setCookie).contains("HttpOnly").contains("SameSite=Strict").contains("Path=/api/auth");
        assertThat(login.getResponse().getContentAsString()).doesNotContain("refresh");
        String access = read(login.getResponse().getContentAsString()).get("accessToken").asText();
        Cookie first = login.getResponse().getCookie("bizaid_refresh");
        // DB에는 원문이 아니라 해시만 있다.
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM refresh_tokens WHERE token_hash = ?", Integer.class, first.getValue()))
                .isZero();
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM refresh_tokens WHERE token_hash = ?", Integer.class,
                HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(first.getValue().getBytes(StandardCharsets.UTF_8)))))
                .isOne();

        mvc.perform(get("/api/auth/me")).andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.error.code").value("auth_required"));
        mvc.perform(get("/api/auth/me").header(HttpHeaders.AUTHORIZATION, "Bearer " + access))
                .andExpect(status().isOk()).andExpect(jsonPath("$.email").value("owner@example.com"));

        MvcResult refreshed = mvc.perform(post("/api/auth/refresh").cookie(first)).andExpect(status().isOk()).andReturn();
        Cookie second = refreshed.getResponse().getCookie("bizaid_refresh");
        assertThat(second.getValue()).isNotEqualTo(first.getValue());

        // 교체된 이전 토큰을 다시 쓰면 거부되고, 탈취 대응으로 새 토큰까지 폐기된다.
        mvc.perform(post("/api/auth/refresh").cookie(first)).andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.error.code").value("auth_refresh_invalid"));
        mvc.perform(post("/api/auth/refresh").cookie(second)).andExpect(status().isUnauthorized());

        MvcResult again = mvc.perform(post("/api/auth/login").contentType(MediaType.APPLICATION_JSON)
                .content("{\"email\":\"owner@example.com\",\"password\":\"password123\"}")).andReturn();
        Cookie third = again.getResponse().getCookie("bizaid_refresh");
        MvcResult logout = mvc.perform(post("/api/auth/logout").cookie(third)).andExpect(status().isNoContent()).andReturn();
        assertThat(logout.getResponse().getHeader(HttpHeaders.SET_COOKIE)).contains("Max-Age=0");
        mvc.perform(post("/api/auth/refresh").cookie(third)).andExpect(status().isUnauthorized());
    }
}
