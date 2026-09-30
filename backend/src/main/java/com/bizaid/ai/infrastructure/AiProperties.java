package com.bizaid.ai.infrastructure;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * FastAPI 내부 AI API 연결 설정. 모두 환경변수로 바꿀 수 있다(AI_BASE_URL, AI_CONNECT_TIMEOUT, AI_RESPONSE_TIMEOUT, INTERNAL_AI_API_KEY).
 * 응답 제한시간(Timeout)이 일반 API보다 긴 이유: 로컬 Qwen 호출이 목록 검색 10~16초, 자격 판정 25~36초로 측정됐다.
 */
@ConfigurationProperties(prefix = "bizaid.ai")
public record AiProperties(String baseUrl, Duration connectTimeout, Duration responseTimeout, String apiKey) {
}
