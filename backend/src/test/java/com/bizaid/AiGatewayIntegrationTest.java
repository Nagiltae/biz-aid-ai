package com.bizaid;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.JsonNode;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

/**
 * 가짜 FastAPI(JDK HttpServer)로 Spring ↔ FastAPI 경계를 확인한다. 실제 Qwen·Qdrant는 부르지 않는다.
 * 확인하는 것: 결과를 바꾸지 않고 전달하는지, 대화에 저장하는지, 제한시간·내부 인증 오류를 서비스 오류로 바꾸는지.
 */
@SpringBootTest
@AutoConfigureMockMvc
class AiGatewayIntegrationTest extends ApiTestSupport {

    record Reply(int status, String body, long delayMillis) {
    }

    record Received(String path, String key, String body) {
    }

    static final HttpServer SERVER = start();
    static volatile Reply reply = new Reply(200, "{}", 0);
    static final List<Received> RECEIVED = new ArrayList<>();

    static HttpServer start() {
        try {
            HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
            server.createContext("/", exchange -> {
                RECEIVED.add(new Received(exchange.getRequestURI().getPath(), exchange.getRequestHeaders().getFirst("X-Internal-Api-Key"),
                        new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8)));
                Reply current = reply;
                try {
                    Thread.sleep(current.delayMillis());
                } catch (InterruptedException exception) {
                    Thread.currentThread().interrupt();
                }
                byte[] bytes = current.body().getBytes(StandardCharsets.UTF_8);
                exchange.getResponseHeaders().add("Content-Type", "application/json");
                try {
                    exchange.sendResponseHeaders(current.status(), bytes.length);
                    exchange.getResponseBody().write(bytes);
                } catch (IOException ignored) {
                    // 제한시간 테스트에서는 Spring이 먼저 연결을 끊으므로 쓰기 실패가 정상이다.
                }
                exchange.close();
            });
            server.start();
            return server;
        } catch (IOException exception) {
            throw new IllegalStateException(exception);
        }
    }

    @DynamicPropertySource
    static void aiProperties(DynamicPropertyRegistry registry) {
        registry.add("bizaid.ai.base-url", () -> "http://127.0.0.1:" + SERVER.getAddress().getPort());
        registry.add("bizaid.ai.response-timeout", () -> "1s");
    }

    @AfterAll
    static void stop() {
        SERVER.stop(0);
    }

    @Autowired
    JdbcTemplate jdbc;

    @BeforeEach
    void reset() {
        RECEIVED.clear();
    }

    private JsonNode ask(String token, String query) throws Exception {
        return read(mvc.perform(post("/api/ai/query").header(HttpHeaders.AUTHORIZATION, token).contentType(MediaType.APPLICATION_JSON)
                        .content(json.writeValueAsString(java.util.Map.of("query", query))))
                .andExpect(status().isOk()).andReturn().getResponse().getContentAsString());
    }

    @Test
    void searchListKeepsFastApiOrderAndIsSavedAsStructuredAssistantMessage() throws Exception {
        String token = signup("list@example.com");
        reply = new Reply(200, """
                {"request_mode":"SEARCH_LIST","status":"LISTED","candidate_count":69,
                 "programs":[{"rank":1,"pblanc_id":"PBLN_000000000000002","name":"두번째 ID지만 1위","category":"금융","target":"소상공인",
                              "jurisdiction_name":"중소벤처기업부","application_start_date":null,"application_period_raw":"예산 소진시까지",
                              "rrf_score":0.0327,"dense_rank":1,"sparse_rank":1,"evidence_chunk_id":"c-2"},
                             {"rank":2,"pblanc_id":"PBLN_000000000000001","name":"첫번째 ID지만 2위","category":"금융","target":"소상공인",
                              "application_start_date":"2026-10-01","application_end_date":"2026-10-16","rrf_score":0.0322}],
                 "natural_filter":{"applied":{"categories":["금융"]}},"candidate_period_unknown":0}""", 0);
        JsonNode body = ask(token, "소상공인 금융 지원사업 찾아줘");

        // Spring은 FastAPI 순위를 그대로 전달한다(ID 순 정렬·재순위 없음).
        assertThat(body.at("/result/requestMode").asText()).isEqualTo("SEARCH_LIST");
        assertThat(body.at("/result/programs/0/pblancId").asText()).isEqualTo("PBLN_000000000000002");
        assertThat(body.at("/result/programs/0/rrfScore").asDouble()).isEqualTo(0.0327);
        assertThat(body.at("/result/programs/1/applicationEndDate").asText()).isEqualTo("2026-10-16");
        // 요청은 snake_case 계약 + 내부 키로 간다.
        assertThat(RECEIVED).singleElement().satisfies(received -> {
            assertThat(received.path()).isEqualTo("/internal/v1/query");
            assertThat(received.key()).isEqualTo("test-internal-key");
            assertThat(read(received.body()).get("query").asText()).isEqualTo("소상공인 금융 지원사업 찾아줘");
        });
        // 목록 결과는 Spring이 답변 문장을 만들지 않고(content 빈 값) 구조화 결과로 저장해 재조회 때 복원한다.
        long conversationId = body.get("conversationId").asLong();
        mvc.perform(get("/api/conversations/" + conversationId + "/messages").header(HttpHeaders.AUTHORIZATION, token))
                .andExpect(jsonPath("$.length()").value(2))
                .andExpect(jsonPath("$[0].role").value("USER"))
                .andExpect(jsonPath("$[1].role").value("ASSISTANT"))
                .andExpect(jsonPath("$[1].content").value(""))
                .andExpect(jsonPath("$[1].resultType").value("SEARCH_LIST"))
                .andExpect(jsonPath("$[1].result.programs[0].pblancId").value("PBLN_000000000000002"));
        // 활동 기록에는 결과 종류·공고 수만 남기고 질문 본문은 넣지 않는다(대화 기준 저장소는 messages).
        String logged = jdbc.queryForObject("SELECT metadata_json FROM activity_logs WHERE action = 'AI_QUERY' AND target_id = ?",
                String.class, String.valueOf(conversationId));
        assertThat(read(logged).get("programCount").asInt()).isEqualTo(2);
        assertThat(logged).contains("SEARCH_LIST").doesNotContain("소상공인 금융");
    }

    @Test
    void documentQaAnswerAndCitationsArePassedAndAnswerBecomesMessageText() throws Exception {
        String token = signup("qa@example.com");
        reply = new Reply(200, """
                {"request_mode":"DOCUMENT_QA","status":"ANSWERED","query":"비즈플러스카드 지원요건","answer":"업력 6개월 이상 개인사업자입니다. [E1]",
                 "citations":[{"evidence_id":"E1","rank":1,"chunk_id":"c-1","pblanc_id":"PBLN_000000000119801","title":"비즈플러스카드 공고",
                               "pages":[3],"source_sha256":"x","source_format":"PDF","heading_path":["2. 지원 요건"],"provenance":[]}],
                 "used_evidence_ids":["E1"],"llm_seconds":12.3}""", 0);
        JsonNode body = ask(token, "비즈플러스카드 지원요건 알려줘");
        assertThat(body.at("/result/status").asText()).isEqualTo("ANSWERED");
        assertThat(body.at("/result/answer").asText()).startsWith("업력 6개월");
        assertThat(body.at("/result/citations/0/pages/0").asInt()).isEqualTo(3);
        assertThat(body.at("/result/citations/0/headingPath/0").asText()).isEqualTo("2. 지원 요건");
        assertThat(body.at("/assistantMessage/content").asText()).isEqualTo(body.at("/result/answer").asText());
    }

    @Test
    void eligibilityStatusCriteriaAndCitationsAreNotRecomputed() throws Exception {
        String token = signup("elig@example.com");
        jdbc.update("INSERT INTO support_programs (id, pblanc_id, name, source_active, source_deleted) VALUES (910, 'PBLN_000000000119801', '비즈플러스카드', true, false)");
        mvc.perform(post("/api/company").header(HttpHeaders.AUTHORIZATION, token).contentType(MediaType.APPLICATION_JSON)
                .content("{\"companyName\":\"판정상사\",\"businessEntityType\":\"개인사업자\",\"businessStartDate\":\"2024-03-01\"}"))
                .andExpect(status().isCreated());
        // 조건이 모두 MET처럼 보여도 FastAPI가 정한 NEEDS_MORE_INFO를 그대로 전달하는지 본다.
        reply = new Reply(200, """
                {"pblanc_id":"PBLN_000000000119801","program_name":"비즈플러스카드","as_of":"2026-10-01","status":"NEEDS_MORE_INFO",
                 "criteria":[{"criterion":"업력 6개월 이상","result":"MET","reason":"업력 31개월","evidence_ids":["E1"],"profile_fields":["business_age_months"],
                              "missing_profile_fields":[],"citations":[{"evidence_id":"E1","pblanc_id":"PBLN_000000000119801","title":"비즈플러스카드",
                              "pages":[3],"location":"p.3","heading_path":["2. 지원 요건"]}]}],
                 "missing_information":["tax_delinquent"],"disclaimer":"사전 판단입니다."}""", 0);
        mvc.perform(post("/api/programs/PBLN_000000000119801/eligibility").header(HttpHeaders.AUTHORIZATION, token)
                        .contentType(MediaType.APPLICATION_JSON).content("{\"creditScore\":720,\"additionalFacts\":{\"최근 2개월 매출(원)\":5000000}}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("NEEDS_MORE_INFO"))
                .andExpect(jsonPath("$.criteria[0].result").value("MET"))
                .andExpect(jsonPath("$.criteria[0].citations[0].location").value("p.3"))
                .andExpect(jsonPath("$.missingInformation[0]").value("tax_delinquent"));
        JsonNode sent = read(RECEIVED.get(0).body());
        assertThat(RECEIVED.get(0).path()).isEqualTo("/internal/v1/eligibility");
        assertThat(sent.get("pblanc_id").asText()).isEqualTo("PBLN_000000000119801");
        assertThat(sent.at("/company_profile/company_name").asText()).isEqualTo("판정상사");
        assertThat(sent.at("/company_profile/credit_score").asInt()).isEqualTo(720);
        assertThat(sent.at("/company_profile/business_start_date").asText()).isEqualTo("2024-03-01");
        assertThat(sent.at("/company_profile/additional_facts/최근 2개월 매출(원)").asLong()).isEqualTo(5_000_000L);
    }

    @Test
    void personalizedSearchSendsOnlySearchCompanyFieldsAndPassesTop3Unchanged() throws Exception {
        String token = signup("personal@example.com");
        mvc.perform(post("/api/ai/personalized-search").header(HttpHeaders.AUTHORIZATION, token).contentType(MediaType.APPLICATION_JSON)
                        .content("{\"query\":\"금융 지원사업\"}"))
                .andExpect(status().isNotFound()).andExpect(jsonPath("$.error.code").value("company_not_registered"));
        mvc.perform(post("/api/company").header(HttpHeaders.AUTHORIZATION, token).contentType(MediaType.APPLICATION_JSON)
                .content("{\"companyName\":\"개인화상사\",\"companySize\":\"소상공인\",\"businessStatus\":\"영업중\","
                        + "\"region\":\"경기도\",\"annualRevenueKrw\":100000000}")).andExpect(status().isCreated());
        reply = new Reply(200, """
                {"status":"LISTED","top_k":3,"as_of":"2026-10-01","candidate_count":4,
                 "programs":[{"rank":1,"pblanc_id":"PBLN_000000000000003","name":"C"},{"rank":2,"pblanc_id":"PBLN_000000000000001","name":"A"}],
                 "applied_conditions":{"company":{"targets":["소상공인","중소기업"]},"query":{"categories":["금융"],"targets":[],"currently_open":false},
                                       "exclude_closed_on":"2026-10-01"},
                 "unapplied_conditions":[{"source":"company","field":"region","value":"경기도","reason":"region_is_not_jurisdiction"}],
                 "natural_filter":{"applied":{"categories":["금융"]}}}""", 0);
        mvc.perform(post("/api/ai/personalized-search").header(HttpHeaders.AUTHORIZATION, token).contentType(MediaType.APPLICATION_JSON)
                        .content("{\"query\":\"우리 회사가 신청할 수 있는 금융 지원사업\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("LISTED"))
                .andExpect(jsonPath("$.programs[0].pblancId").value("PBLN_000000000000003"))
                .andExpect(jsonPath("$.appliedConditions.company.targets[1]").value("중소기업"))
                .andExpect(jsonPath("$.unappliedConditions[0].reason").value("region_is_not_jurisdiction"));
        Received sent = RECEIVED.get(RECEIVED.size() - 1);
        assertThat(sent.path()).isEqualTo("/internal/v2/personalized-search");
        // 검색에 필요한 기업정보 4개만 보낸다(연 매출·회사명 등은 보내지 않는다). FastAPI는 회사 DB를 읽지 않는다.
        JsonNode profile = read(sent.body()).get("company_profile");
        assertThat(profile.fieldNames()).toIterable().containsExactlyInAnyOrder("company_size", "business_status", "region",
                "business_start_date");
        assertThat(profile.get("company_size").asText()).isEqualTo("소상공인");
        // Top 3 계약을 어긴 응답(4개)은 잘라내지 않고 거부한다.
        reply = new Reply(200, "{\"status\":\"LISTED\",\"candidate_count\":9,\"programs\":[{\"pblanc_id\":\"P1\"},{\"pblanc_id\":\"P2\"},"
                + "{\"pblanc_id\":\"P3\"},{\"pblanc_id\":\"P4\"}]}", 0);
        mvc.perform(post("/api/ai/personalized-search").header(HttpHeaders.AUTHORIZATION, token).contentType(MediaType.APPLICATION_JSON)
                        .content("{\"query\":\"금융\"}"))
                .andExpect(status().isBadGateway()).andExpect(jsonPath("$.error.code").value("ai_response_invalid"));
    }

    @Test
    void top3EligibilityKeepsSearchOrderAndPerProgramFailuresWithStoredCompanyFactsOnly() throws Exception {
        String token = signup("top3@example.com");
        mvc.perform(post("/api/company").header(HttpHeaders.AUTHORIZATION, token).contentType(MediaType.APPLICATION_JSON)
                .content("{\"companyName\":\"판정상사\",\"businessEntityType\":\"개인사업자\",\"companySize\":\"소상공인\","
                        + "\"businessStatus\":\"영업중\",\"employeeCount\":3}")).andExpect(status().isCreated());
        String search = "{\"status\":\"LISTED\",\"candidate_count\":9,\"programs\":[{\"rank\":1,\"pblanc_id\":\"PBLN_C\"},"
                + "{\"rank\":2,\"pblanc_id\":\"PBLN_A\"},{\"rank\":3,\"pblanc_id\":\"PBLN_B\"}]}";
        reply = new Reply(200, "{\"search\":" + search + ",\"evaluations\":["
                + "{\"rank\":1,\"pblanc_id\":\"PBLN_C\",\"evaluation_status\":\"COMPLETED\",\"error_code\":null,"
                + "\"eligibility\":{\"pblanc_id\":\"PBLN_C\",\"status\":\"ELIGIBLE\",\"criteria\":[],\"missing_information\":[]}},"
                + "{\"rank\":2,\"pblanc_id\":\"PBLN_A\",\"evaluation_status\":\"COMPLETED\",\"error_code\":null,"
                + "\"eligibility\":{\"pblanc_id\":\"PBLN_A\",\"status\":\"NEEDS_MORE_INFO\",\"criteria\":[{\"criterion\":\"신용점수\","
                + "\"result\":\"UNKNOWN\",\"citations\":[{\"evidence_id\":\"E1\",\"pblanc_id\":\"PBLN_A\",\"location\":\"p.3\"}]}],"
                + "\"missing_information\":[\"credit_score\"]}},"
                + "{\"rank\":3,\"pblanc_id\":\"PBLN_B\",\"evaluation_status\":\"FAILED\",\"error_code\":\"llm_unavailable\",\"eligibility\":null}]}", 0);
        mvc.perform(post("/api/ai/personalized-eligibility").header(HttpHeaders.AUTHORIZATION, token)
                        .contentType(MediaType.APPLICATION_JSON).content("{\"query\":\"우리 회사가 신청할 수 있는 금융 지원사업\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.evaluations[0].eligibility.status").value("ELIGIBLE"))
                .andExpect(jsonPath("$.evaluations[1].eligibility.missingInformation[0]").value("credit_score"))
                .andExpect(jsonPath("$.evaluations[1].eligibility.criteria[0].citations[0].location").value("p.3"))
                .andExpect(jsonPath("$.evaluations[2].evaluationStatus").value("FAILED"))
                .andExpect(jsonPath("$.evaluations[2].errorCode").value("llm_unavailable"));
        Received sent = RECEIVED.get(RECEIVED.size() - 1);
        JsonNode profile = read(sent.body()).get("company_profile");
        assertThat(sent.path()).isEqualTo("/internal/v2/personalized-eligibility");
        // 저장된 기업정보만 보내고, 저장되지 않은 신용점수·체납은 만들지 않는다(null → 판정에서 판단 불가).
        assertThat(profile.get("company_name").asText()).isEqualTo("판정상사");
        assertThat(profile.get("employee_count").asInt()).isEqualTo(3);
        assertThat(profile.get("credit_score").isNull()).isTrue();
        assertThat(profile.get("tax_delinquent").isNull()).isTrue();
        // 판정 순서가 검색 Top 3 순서와 다르면 Spring이 고쳐 쓰지 않고 거부한다.
        reply = new Reply(200, "{\"search\":" + search + ",\"evaluations\":["
                + "{\"rank\":2,\"pblanc_id\":\"PBLN_A\",\"evaluation_status\":\"FAILED\",\"error_code\":\"x\"},"
                + "{\"rank\":1,\"pblanc_id\":\"PBLN_C\",\"evaluation_status\":\"FAILED\",\"error_code\":\"x\"},"
                + "{\"rank\":3,\"pblanc_id\":\"PBLN_B\",\"evaluation_status\":\"FAILED\",\"error_code\":\"x\"}]}", 0);
        mvc.perform(post("/api/ai/personalized-eligibility").header(HttpHeaders.AUTHORIZATION, token)
                        .contentType(MediaType.APPLICATION_JSON).content("{\"query\":\"금융\"}"))
                .andExpect(status().isBadGateway()).andExpect(jsonPath("$.error.code").value("ai_response_invalid"));
    }

    @Test
    void timeoutAndInternalAuthFailureBecomeServiceErrorsWithoutFakeAssistantMessage() throws Exception {
        String token = signup("fail@example.com");
        reply = new Reply(200, "{\"request_mode\":\"SEARCH_LIST\",\"status\":\"LISTED\",\"programs\":[]}", 2_000);
        String body = mvc.perform(post("/api/ai/query").header(HttpHeaders.AUTHORIZATION, token).contentType(MediaType.APPLICATION_JSON)
                        .content("{\"query\":\"느린 질문\"}"))
                .andExpect(status().isGatewayTimeout()).andExpect(jsonPath("$.error.code").value("ai_service_timeout"))
                .andReturn().getResponse().getContentAsString();
        assertThat(body).doesNotContain("127.0.0.1");
        long conversationId = read(mvc.perform(get("/api/conversations").header(HttpHeaders.AUTHORIZATION, token))
                .andReturn().getResponse().getContentAsString()).get(0).get("id").asLong();
        // 실패하면 질문만 남고 ASSISTANT 메시지는 저장하지 않는다.
        mvc.perform(get("/api/conversations/" + conversationId + "/messages").header(HttpHeaders.AUTHORIZATION, token))
                .andExpect(jsonPath("$.length()").value(1)).andExpect(jsonPath("$[0].role").value("USER"));
        assertThat(jdbc.queryForObject("SELECT error_code FROM activity_logs WHERE action = 'AI_QUERY' AND success = false"
                + " AND target_id = ?", String.class, String.valueOf(conversationId))).isEqualTo("ai_service_timeout");

        // FastAPI 내부 인증 실패(401)는 사용자 로그인 실패가 아니라 서비스 설정 오류(502)다.
        reply = new Reply(401, "{\"error\":{\"code\":\"internal_auth_failed\"}}", 0);
        mvc.perform(post("/api/ai/query").header(HttpHeaders.AUTHORIZATION, token).contentType(MediaType.APPLICATION_JSON)
                        .content("{\"query\":\"질문\",\"conversationId\":" + conversationId + "}"))
                .andExpect(status().isBadGateway()).andExpect(jsonPath("$.error.code").value("ai_service_auth_failed"));
    }
}
