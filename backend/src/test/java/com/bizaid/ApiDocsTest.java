package com.bizaid;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;

/** dev profile처럼 문서를 켜면 로그인 없이 API 문서를 읽을 수 있고, 새 계정 관리 API가 들어 있다. */
@SpringBootTest(properties = {"springdoc.api-docs.enabled=true", "springdoc.swagger-ui.enabled=true"})
@AutoConfigureMockMvc
class ApiDocsTest extends ApiTestSupport {

    @Test
    void openApiDocumentListsServiceEndpoints() throws Exception {
        mvc.perform(get("/v3/api-docs"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.info.title").value("BizAid 서비스 API"))
                .andExpect(jsonPath("$.paths['/api/account/withdraw']").exists())
                .andExpect(jsonPath("$.paths['/api/conversations/{conversationId}'].delete").exists())
                .andExpect(jsonPath("$.paths['/api/ai/workflows'].get").exists());
    }
}
