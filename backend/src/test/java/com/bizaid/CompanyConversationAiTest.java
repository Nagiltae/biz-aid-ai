package com.bizaid;

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
        mvc.perform(post("/api/company").header(HttpHeaders.AUTHORIZATION, token).contentType(MediaType.APPLICATION_JSON)
                        .content("{\"companyName\":\"비즈에이드\",\"businessEntityType\":\"법인\",\"region\":\"경기도\","
                                + "\"businessStartDate\":\"2023-03-02\",\"employeeCount\":5}"))
                .andExpect(status().isCreated()).andExpect(jsonPath("$.companyName").value("비즈에이드"));
        mvc.perform(post("/api/company").header(HttpHeaders.AUTHORIZATION, token).contentType(MediaType.APPLICATION_JSON)
                        .content("{\"companyName\":\"두번째\"}"))
                .andExpect(status().isConflict()).andExpect(jsonPath("$.error.code").value("company_already_registered"));
        mvc.perform(put("/api/company").header(HttpHeaders.AUTHORIZATION, token).contentType(MediaType.APPLICATION_JSON)
                        .content("{\"companyName\":\"비즈에이드\",\"businessEntityType\":\"법인\",\"exporter\":true}"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.exporter").value(true))
                .andExpect(jsonPath("$.region").doesNotExist());
        mvc.perform(get("/api/company").header(HttpHeaders.AUTHORIZATION, token))
                .andExpect(status().isOk()).andExpect(jsonPath("$.exporter").value(true));
    }

    @Test
    void conversationMessagesAreSavedAndHiddenFromOtherUsers() throws Exception {
        String owner = signup("chat@example.com");
        String other = signup("other@example.com");
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
        mvc.perform(post("/api/ai/query").header(HttpHeaders.AUTHORIZATION, token).contentType(MediaType.APPLICATION_JSON)
                        .content("{\"query\":\"소상공인 금융 지원사업 찾아줘\"}"))
                .andExpect(status().isServiceUnavailable()).andExpect(jsonPath("$.error.code").value("ai_service_unavailable"));

        jdbc.update("INSERT INTO support_programs (id, pblanc_id, name, source_active, source_deleted) VALUES (900, 'PBLN_900', '판정 대상', true, false)");
        String path = "/api/programs/PBLN_900/eligibility";
        mvc.perform(post(path).header(HttpHeaders.AUTHORIZATION, token).contentType(MediaType.APPLICATION_JSON).content("{}"))
                .andExpect(status().isNotFound()).andExpect(jsonPath("$.error.code").value("company_not_registered"));
        mvc.perform(post("/api/company").header(HttpHeaders.AUTHORIZATION, token).contentType(MediaType.APPLICATION_JSON)
                .content("{\"companyName\":\"판정기업\"}")).andExpect(status().isCreated());
        mvc.perform(post("/api/programs/PBLN_MISSING/eligibility").header(HttpHeaders.AUTHORIZATION, token)
                        .contentType(MediaType.APPLICATION_JSON).content("{}"))
                .andExpect(status().isNotFound()).andExpect(jsonPath("$.error.code").value("program_not_found"));
        mvc.perform(post(path).header(HttpHeaders.AUTHORIZATION, token).contentType(MediaType.APPLICATION_JSON)
                        .content("{\"creditScore\":700,\"taxDelinquent\":false}"))
                .andExpect(status().isServiceUnavailable()).andExpect(jsonPath("$.error.code").value("ai_service_unavailable"));
    }
}
