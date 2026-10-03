package com.bizaid;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootTest
@AutoConfigureMockMvc
class CompanyConversationAiTest extends ApiTestSupport {

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void companyIsRegisteredReadAndUpdatedOnlyForOwner() throws Exception {
        String token = signup("company@example.com");
        mvc.perform(get("/api/company").header(HttpHeaders.AUTHORIZATION, token))
                .andExpect(status().isNotFound()).andExpect(jsonPath("$.error.code").value("company_not_registered"));
        mvc.perform(post("/api/company").header(HttpHeaders.AUTHORIZATION, token).contentType(MediaType.APPLICATION_JSON)
                        .content("{\"companyName\":\"\",\"businessEntityType\":\"주식회사\"}"))
                .andExpect(status().isBadRequest()).andExpect(jsonPath("$.error.code").value("validation_failed"))
                .andExpect(jsonPath("$.error.fieldErrors.length()").value(2));
        // 기업 규모는 선택지(소상공인·중소기업·중견기업)만 받는다.
        mvc.perform(post("/api/company").header(HttpHeaders.AUTHORIZATION, token).contentType(MediaType.APPLICATION_JSON)
                        .content("{\"companyName\":\"비즈에이드\",\"companySize\":\"대기업\"}"))
                .andExpect(status().isBadRequest()).andExpect(jsonPath("$.error.fieldErrors[0].field").value("companySize"));
        // 지역은 공통 계약의 광역 지자체 표준명만 받는다. 자유 입력·통합 전 이름은 거부한다(2026-10-03, IMP-019).
        for (String region : new String[] {"경기도 광명시", "광주광역시", "서울"}) {
            mvc.perform(post("/api/company").header(HttpHeaders.AUTHORIZATION, token).contentType(MediaType.APPLICATION_JSON)
                            .content("{\"companyName\":\"비즈에이드\",\"region\":\"" + region + "\"}"))
                    .andExpect(status().isBadRequest()).andExpect(jsonPath("$.error.fieldErrors[0].field").value("region"));
        }
        mvc.perform(get("/api/company/regions").header(HttpHeaders.AUTHORIZATION, token))
                .andExpect(status().isOk()).andExpect(jsonPath("$.regions.length()").value(16))
                .andExpect(jsonPath("$.regions[0]").value("서울특별시"))
                .andExpect(jsonPath("$.regions[?(@ == '전남광주통합특별시')]").exists());
        mvc.perform(post("/api/company").header(HttpHeaders.AUTHORIZATION, token).contentType(MediaType.APPLICATION_JSON)
                        .content("{\"companyName\":\"비즈에이드\",\"businessEntityType\":\"법인\",\"region\":\"경기도\","
                                + "\"businessStartDate\":\"2023-03-02\",\"employeeCount\":5}"))
                .andExpect(status().isCreated()).andExpect(jsonPath("$.companyName").value("비즈에이드"));
        mvc.perform(post("/api/company").header(HttpHeaders.AUTHORIZATION, token).contentType(MediaType.APPLICATION_JSON)
                        .content("{\"companyName\":\"두번째\"}"))
                .andExpect(status().isConflict()).andExpect(jsonPath("$.error.code").value("company_already_registered"));
        mvc.perform(put("/api/company").header(HttpHeaders.AUTHORIZATION, token).contentType(MediaType.APPLICATION_JSON)
                        .content("{\"companyName\":\"비즈에이드\",\"businessEntityType\":\"법인\",\"companySize\":\"중견기업\",\"exporter\":true}"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.exporter").value(true)).andExpect(jsonPath("$.companySize").value("중견기업"))
                .andExpect(jsonPath("$.region").doesNotExist());
        mvc.perform(get("/api/company").header(HttpHeaders.AUTHORIZATION, token))
                .andExpect(status().isOk()).andExpect(jsonPath("$.exporter").value(true));
    }

    @Test
    void conversationMessagesAreSavedAndHiddenFromOtherUsers() throws Exception {
        String owner = signupWithCompany("chat@example.com");
        String other = signupWithCompany("other@example.com");
        String created = mvc.perform(post("/api/conversations").header(HttpHeaders.AUTHORIZATION, owner)
                        .contentType(MediaType.APPLICATION_JSON).content("{\"title\":\"금융 지원사업\"}"))
                .andExpect(status().isCreated()).andReturn().getResponse().getContentAsString();
        long id = read(created).get("id").asLong();
        mvc.perform(post("/api/conversations/" + id + "/messages").header(HttpHeaders.AUTHORIZATION, owner)
                        .contentType(MediaType.APPLICATION_JSON).content("{\"content\":\"소상공인 금융 지원사업 찾아줘\"}"))
                .andExpect(status().isCreated()).andExpect(jsonPath("$.role").value("USER"));
        mvc.perform(get("/api/conversations/" + id + "/messages").header(HttpHeaders.AUTHORIZATION, owner))
                .andExpect(status().isOk()).andExpect(jsonPath("$.length()").value(1))
                .andExpect(jsonPath("$[0].content").value("소상공인 금융 지원사업 찾아줘"));
        mvc.perform(get("/api/conversations").header(HttpHeaders.AUTHORIZATION, owner))
                .andExpect(jsonPath("$[0].title").value("금융 지원사업"));
        mvc.perform(get("/api/conversations/" + id + "/messages").header(HttpHeaders.AUTHORIZATION, other))
                .andExpect(status().isNotFound()).andExpect(jsonPath("$.error.code").value("conversation_not_found"));
    }

    @Test
    void aiEndpointsReportUnavailableAiInsteadOfInventingResults() throws Exception {
        String token = signup("ai@example.com");
        mvc.perform(post("/api/ai/query").contentType(MediaType.APPLICATION_JSON).content("{\"query\":\"금융 지원\"}"))
                .andExpect(status().isUnauthorized());
        // BOUNDARY: 기업정보 없는 AI 검색은 전체 범위로 호출한다. AI 서버 오류는 성공 결과로 숨기지 않는다.
        mvc.perform(post("/api/ai/query").header(HttpHeaders.AUTHORIZATION, token).contentType(MediaType.APPLICATION_JSON)
                        .content("{\"query\":\"소상공인 금융 지원사업 찾아줘\"}"))
                .andExpect(status().isServiceUnavailable()).andExpect(jsonPath("$.error.code").value("ai_service_unavailable"));
        mvc.perform(get("/api/conversations").header(HttpHeaders.AUTHORIZATION, token)).andExpect(status().isOk());
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM conversations c JOIN users u ON u.id = c.user_id "
                + "WHERE u.email = 'ai@example.com'", Integer.class)).isOne();

        jdbc.update("INSERT INTO support_programs (id, pblanc_id, name, source_active, source_deleted) VALUES (900, 'PBLN_900', '판정 대상', true, false)");
        String path = "/api/programs/PBLN_900/eligibility";
        mvc.perform(post(path).header(HttpHeaders.AUTHORIZATION, token).contentType(MediaType.APPLICATION_JSON).content("{}"))
                .andExpect(status().isNotFound()).andExpect(jsonPath("$.error.code").value("company_not_registered"));
        mvc.perform(post("/api/company").header(HttpHeaders.AUTHORIZATION, token).contentType(MediaType.APPLICATION_JSON)
                .content("{\"companyName\":\"판정기업\"}")).andExpect(status().isCreated());
        mvc.perform(post("/api/ai/query").header(HttpHeaders.AUTHORIZATION, token).contentType(MediaType.APPLICATION_JSON)
                        .content("{\"query\":\"소상공인 금융 지원사업 찾아줘\"}"))
                .andExpect(status().isServiceUnavailable()).andExpect(jsonPath("$.error.code").value("ai_service_unavailable"));
        mvc.perform(post("/api/programs/PBLN_MISSING/eligibility").header(HttpHeaders.AUTHORIZATION, token)
                        .contentType(MediaType.APPLICATION_JSON).content("{}"))
                .andExpect(status().isNotFound()).andExpect(jsonPath("$.error.code").value("program_not_found"));
        mvc.perform(post(path).header(HttpHeaders.AUTHORIZATION, token).contentType(MediaType.APPLICATION_JSON)
                        .content("{\"creditScore\":700,\"taxDelinquent\":false}"))
                .andExpect(status().isServiceUnavailable()).andExpect(jsonPath("$.error.code").value("ai_service_unavailable"));
    }
}
