package com.bizaid;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Autowired;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

/** API 테스트 공통 도우미: 회원가입으로 Access Token을 받아 Bearer 헤더 값을 돌려준다. */
public abstract class ApiTestSupport {

    @Autowired
    protected MockMvc mvc;

    @Autowired
    protected ObjectMapper json;

    @Autowired
    private JdbcTemplate usageJdbc;

    @BeforeEach
    void resetUsageFixture() {
        // BOUNDARY: H2 테스트 DB의 counter만 격리한다. 한 테스트 안의 동시 요청·상한 검사는 그대로다.
        usageJdbc.update("delete from ai_usage_counters");
    }

    protected String signup(String email) throws Exception {
        String body = mvc.perform(post("/api/auth/signup").contentType(MediaType.APPLICATION_JSON)
                        .content("{\"email\":\"" + email + "\",\"password\":\"password123\",\"displayName\":\"테스터\",\"agreeTerms\":true,\"agreePrivacy\":true}"))
                .andExpect(status().isOk()).andReturn().getResponse().getContentAsString();
        return "Bearer " + read(body).get("accessToken").asText();
    }

    /** AI 검색·대화처럼 기업정보가 있어야 쓰는 기능을 테스트할 때: 가입 뒤 최소 기업정보(회사명)를 등록한다. */
    protected String signupWithCompany(String email) throws Exception {
        String token = signup(email);
        mvc.perform(post("/api/company").header(HttpHeaders.AUTHORIZATION, token).contentType(MediaType.APPLICATION_JSON)
                .content("{\"companyName\":\"테스트상사\"}")).andExpect(status().isCreated());
        return token;
    }

    protected JsonNode read(String body) throws Exception {
        return json.readTree(body);
    }
}
