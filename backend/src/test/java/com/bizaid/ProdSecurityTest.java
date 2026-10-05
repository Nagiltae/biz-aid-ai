package com.bizaid;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;

/** 운영 profile의 공개 표면만 H2로 확인한다. RDS·사용자 Secret·실제 AI에 연결하지 않는다. */
@SpringBootTest(properties = {"spring.profiles.active=prod", "spring.datasource.url=jdbc:h2:mem:prodsecurity;MODE=MySQL;DATABASE_TO_LOWER=TRUE;DB_CLOSE_DELAY=-1",
        "spring.flyway.locations=filesystem:../migrations", "bizaid.ai.base-url=http://127.0.0.1:9"})
@AutoConfigureMockMvc
class ProdSecurityTest extends ApiTestSupport {
    @Test
    void productionSwaggerAndInternalDetailsAreNotExposed() throws Exception {
        mvc.perform(get("/api/health")).andExpect(status().isOk()).andExpect(jsonPath("$.status").value("ok"));
        for (String path : new String[] {"/v3/api-docs", "/swagger-ui/index.html"}) {
            mvc.perform(get(path)).andExpect(status().isNotFound()).andExpect(jsonPath("$.error.code").value("not_found"));
        }
    }
}
