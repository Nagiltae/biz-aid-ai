package com.bizaid;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;

/** 운영 설정으로 체험하기를 끄면 상태 API가 false이고 시작 요청은 고정 코드로 거부된다. */
@SpringBootTest(properties = "bizaid.usage.trial.enabled=false")
@AutoConfigureMockMvc
class TrialDisabledTest extends ApiTestSupport {

    @Test
    void trialCanBeSwitchedOffBySetting() throws Exception {
        mvc.perform(get("/api/auth/trial")).andExpect(status().isOk()).andExpect(jsonPath("$.enabled").value(false));
        mvc.perform(post("/api/auth/trial")).andExpect(status().isForbidden()).andExpect(jsonPath("$.error.code").value("trial_disabled"));
    }
}
