package com.bizaid.ai;

import com.bizaid.common.ApiException;
import com.bizaid.common.ErrorCode;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import java.io.IOException;
import java.io.InputStream;
import java.net.ConnectException;
import java.net.http.HttpClient;
import java.net.http.HttpConnectTimeoutException;
import java.net.http.HttpTimeoutException;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;
import java.util.stream.Stream;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.MediaType;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;

/**
 * FastAPI 내부 AI API를 HTTP로 호출하는 AI 연결 창구(AiGateway) 구현.
 *
 * <p>WHY 동기 RestClient: 서비스가 Spring MVC(요청당 스레드)라 WebFlux를 새로 들이지 않고 Spring 6 기본 동기 client로 충분하다.
 * <p>BOUNDARY: 요청을 보내고 응답이 계약대로인지 검증만 한다. 답변·목록 순위·자격 상태·근거를 다시 계산하거나 고치지 않는다.
 * 계약을 어긴 응답은 고쳐 쓰지 않고 ai_response_invalid로 거부한다.
 * <p>자동 재시도(retry) 없음: 같은 LLM 요청이 중복 실행되고 대기 시간이 길어지며 메시지가 이중 저장될 수 있다. 사용자가 직접 다시 시도한다.
 */
@Component
public class HttpAiGateway implements AiGateway {

    static final String KEY_HEADER = "X-Internal-Api-Key";
    private static final Logger log = LoggerFactory.getLogger(HttpAiGateway.class);
    private static final Set<String> REQUEST_MODES = Set.of("SEARCH_LIST", "DOCUMENT_QA");
    private static final Set<String> ELIGIBILITY_STATUSES = Set.of("ELIGIBLE", "INELIGIBLE", "NEEDS_MORE_INFO", "INSUFFICIENT_EVIDENCE");

    private final RestClient client;
    private final ObjectMapper snakeCase;
    private final String apiKey;

    public HttpAiGateway(AiProperties properties, ObjectMapper objectMapper) {
        // 연결 제한시간은 짧게(서버가 꺼져 있으면 빨리 알림), 응답 제한시간은 길게(LLM 생성 시간) 따로 둔다.
        HttpClient httpClient = HttpClient.newBuilder().connectTimeout(properties.connectTimeout())
                .version(HttpClient.Version.HTTP_1_1).build();
        JdkClientHttpRequestFactory factory = new JdkClientHttpRequestFactory(httpClient);
        factory.setReadTimeout(properties.responseTimeout());
        this.client = RestClient.builder().baseUrl(properties.baseUrl()).requestFactory(factory).build();
        // FastAPI JSON(snake_case) ↔ Java(camelCase) 이름 규칙만 바꾼다. 모르는 field는 무시해 FastAPI가 field를 추가해도 깨지지 않는다.
        this.snakeCase = objectMapper.copy().setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
                .configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false);
        this.apiKey = properties.apiKey() == null ? "" : properties.apiKey();
    }

    @Override
    public AiDtos.AiQueryResult query(String query) {
        AiDtos.AiQueryResult result = post("/internal/v1/query", new AiDtos.QueryPayload(query), AiDtos.AiQueryResult.class);
        if (result == null || !REQUEST_MODES.contains(result.requestMode()) || result.status() == null) {
            throw invalid("query: unknown request_mode or missing status");
        }
        if (result.programs() != null) {
            Set<String> seen = new HashSet<>();
            // 목록은 공고 단위다. 중복이 오면 Spring이 지우지 않고(순위 변경이 되므로) 계약 위반으로 거부한다.
            if (!result.programs().stream().allMatch(program -> program.pblancId() != null && seen.add(program.pblancId()))) {
                throw invalid("query: duplicate or missing pblanc_id in programs");
            }
        }
        return result;
    }

    @Override
    public AiDtos.EligibilityResult evaluateEligibility(AiDtos.EligibilityCommand command) {
        AiDtos.EligibilityResult result = post("/internal/v1/eligibility",
                new AiDtos.EligibilityPayload(command.pblancId(), command.companyProfile()), AiDtos.EligibilityResult.class);
        if (result == null || !ELIGIBILITY_STATUSES.contains(result.status()) || !command.pblancId().equals(result.pblancId())) {
            throw invalid("eligibility: unknown status or different pblanc_id");
        }
        // BOUNDARY: 판정 근거는 요청한 공고의 공고문에서만 와야 한다. 다른 공고 근거가 섞이면 결과를 쓰지 않는다.
        boolean scoped = result.criteria() == null || result.criteria().stream()
                .flatMap(criterion -> criterion.citations() == null ? Stream.empty() : criterion.citations().stream())
                .allMatch(citation -> command.pblancId().equals(citation.pblancId()));
        if (!scoped) {
            throw invalid("eligibility: citation outside the target program");
        }
        return result;
    }

    private <T> T post(String path, Object body, Class<T> type) {
        byte[] payload;
        try {
            payload = snakeCase.writeValueAsBytes(body);
        } catch (IOException exception) {
            throw new IllegalStateException(exception);
        }
        try {
            return client.post().uri(path).contentType(MediaType.APPLICATION_JSON).accept(MediaType.APPLICATION_JSON)
                    .header(KEY_HEADER, apiKey).body(payload)
                    .exchange((request, response) -> {
                        int status = response.getStatusCode().value();
                        if (status >= 200 && status < 300) {
                            return read(response.getBody(), type);
                        }
                        throw mapError(path, status, errorCode(response.getBody()));
                    });
        } catch (ResourceAccessException exception) {
            throw mapIo(path, exception);
        }
    }

    private <T> T read(InputStream body, Class<T> type) {
        try {
            return snakeCase.readValue(body, type);
        } catch (IOException exception) {
            throw invalid("response is not the contracted JSON");
        }
    }

    private String errorCode(InputStream body) {
        try {
            JsonNode node = snakeCase.readTree(body);
            return node == null ? null : node.path("error").path("code").asText(null);
        } catch (IOException exception) {
            return null;
        }
    }

    /**
     * FastAPI HTTP 오류를 서비스 공통 오류로 바꾼다. FastAPI 오류 code는 로그에만 남기고 React에는 내부 사정(Ollama·Qdrant·DB 상세)을 보내지 않는다.
     * 401/403은 최종 사용자의 로그인 문제가 아니라 Spring↔FastAPI 공유 키 설정 문제라 502 ai_service_auth_failed로 바꾼다.
     */
    ApiException mapError(String path, int status, String upstreamCode) {
        log.warn("AI upstream error path={} status={} code={}", path, status, upstreamCode);
        ErrorCode code = switch (status) {
            case 401, 403 -> ErrorCode.AI_SERVICE_AUTH_FAILED;
            case 404 -> Objects.equals(upstreamCode, "eligibility_program_not_found_or_inactive")
                    ? ErrorCode.PROGRAM_NOT_FOUND : ErrorCode.AI_SERVICE_ERROR;
            case 502 -> ErrorCode.AI_RESPONSE_INVALID;
            case 503 -> Objects.equals(upstreamCode, "internal_auth_not_configured")
                    ? ErrorCode.AI_SERVICE_AUTH_FAILED : ErrorCode.AI_SERVICE_UNAVAILABLE;
            default -> ErrorCode.AI_SERVICE_ERROR;
        };
        return new ApiException(code);
    }

    private ApiException mapIo(String path, ResourceAccessException exception) {
        Throwable cause = exception.getCause();
        // HttpConnectTimeoutException은 HttpTimeoutException의 하위 타입이다. 연결 실패(서버 없음)를 응답 지연보다 먼저 가른다.
        boolean connect = cause instanceof ConnectException || cause instanceof HttpConnectTimeoutException;
        boolean timeout = !connect && cause instanceof HttpTimeoutException;
        log.warn("AI upstream io failure path={} type={}", path, cause == null ? "unknown" : cause.getClass().getSimpleName());
        return new ApiException(timeout ? ErrorCode.AI_SERVICE_TIMEOUT : ErrorCode.AI_SERVICE_UNAVAILABLE);
    }

    private ApiException invalid(String reason) {
        log.warn("AI response rejected: {}", reason);
        return new ApiException(ErrorCode.AI_RESPONSE_INVALID);
    }
}
