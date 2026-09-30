package com.bizaid.common;

import org.springframework.http.HttpStatus;

/**
 * API 오류 코드 목록.
 * React는 code로 분기하고 message는 사용자에게 그대로 보여 준다.
 * code 문자열은 FastAPI 내부 API와 같은 소문자 snake_case 형식으로 맞춰 오류 규칙을 하나로 유지한다.
 */
public enum ErrorCode {
    VALIDATION_FAILED(HttpStatus.BAD_REQUEST, "validation_failed", "입력값을 확인해 주세요."),
    MALFORMED_REQUEST(HttpStatus.BAD_REQUEST, "malformed_request", "요청 형식이 올바르지 않습니다."),
    NOT_FOUND(HttpStatus.NOT_FOUND, "not_found", "요청한 주소를 찾을 수 없습니다."),
    METHOD_NOT_ALLOWED(HttpStatus.METHOD_NOT_ALLOWED, "method_not_allowed", "지원하지 않는 요청 방식입니다."),
    AUTH_REQUIRED(HttpStatus.UNAUTHORIZED, "auth_required", "로그인이 필요합니다."),
    AUTH_INVALID_CREDENTIALS(HttpStatus.UNAUTHORIZED, "auth_invalid_credentials", "이메일 또는 비밀번호가 올바르지 않습니다."),
    AUTH_REFRESH_INVALID(HttpStatus.UNAUTHORIZED, "auth_refresh_invalid", "로그인이 만료되었습니다. 다시 로그인해 주세요."),
    AUTH_EMAIL_TAKEN(HttpStatus.CONFLICT, "auth_email_taken", "이미 가입된 이메일입니다."),
    COMPANY_NOT_REGISTERED(HttpStatus.NOT_FOUND, "company_not_registered", "등록된 기업정보가 없습니다. 먼저 기업정보를 등록해 주세요."),
    COMPANY_ALREADY_REGISTERED(HttpStatus.CONFLICT, "company_already_registered", "이미 기업정보가 등록되어 있습니다. 수정 기능을 사용해 주세요."),
    PROGRAM_NOT_FOUND(HttpStatus.NOT_FOUND, "program_not_found", "지원사업을 찾을 수 없거나 더 이상 게시되지 않는 공고입니다."),
    CONVERSATION_NOT_FOUND(HttpStatus.NOT_FOUND, "conversation_not_found", "대화를 찾을 수 없습니다."),
    // AI(FastAPI) 호출 오류. 모두 서버 쪽 문제라 사용자 로그인 오류(401)와 구분되는 5xx로 돌려준다.
    AI_SERVICE_UNAVAILABLE(HttpStatus.SERVICE_UNAVAILABLE, "ai_service_unavailable",
            "AI 서비스에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요."),
    AI_SERVICE_TIMEOUT(HttpStatus.GATEWAY_TIMEOUT, "ai_service_timeout",
            "AI 응답이 제한시간 안에 오지 않았습니다. 잠시 후 다시 시도해 주세요."),
    AI_SERVICE_AUTH_FAILED(HttpStatus.BAD_GATEWAY, "ai_service_auth_failed",
            "AI 서비스 연결 설정에 문제가 있습니다. 관리자에게 문의해 주세요."),
    AI_RESPONSE_INVALID(HttpStatus.BAD_GATEWAY, "ai_response_invalid",
            "AI 응답 형식이 올바르지 않아 결과를 보여 줄 수 없습니다. 다시 시도해 주세요."),
    AI_SERVICE_ERROR(HttpStatus.BAD_GATEWAY, "ai_service_error",
            "AI 서비스에서 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."),
    INTERNAL_ERROR(HttpStatus.INTERNAL_SERVER_ERROR, "internal_error", "일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.");

    private final HttpStatus status;
    private final String code;
    private final String message;

    ErrorCode(HttpStatus status, String code, String message) {
        this.status = status;
        this.code = code;
        this.message = message;
    }

    public HttpStatus status() {
        return status;
    }

    public String code() {
        return code;
    }

    public String message() {
        return message;
    }
}
