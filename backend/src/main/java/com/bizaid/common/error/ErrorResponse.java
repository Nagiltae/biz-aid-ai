package com.bizaid.common.error;

import com.fasterxml.jackson.annotation.JsonInclude;
import java.util.List;

/**
 * 모든 API 오류의 공통 본문: {"error": {"code", "message", "fieldErrors"}}.
 * 정상 응답은 wrapper 없이 DTO를 그대로 돌려주고, 오류만 이 한 가지 형태로 통일한다.
 */
public record ErrorResponse(Body error) {

    @JsonInclude(JsonInclude.Include.NON_EMPTY)
    public record Body(String code, String message, List<FieldError> fieldErrors) {
    }

    public record FieldError(String field, String message) {
    }

    public static ErrorResponse of(ErrorCode errorCode) {
        return new ErrorResponse(new Body(errorCode.code(), errorCode.message(), List.of()));
    }

    public static ErrorResponse of(ErrorCode errorCode, List<FieldError> fieldErrors) {
        return new ErrorResponse(new Body(errorCode.code(), errorCode.message(), fieldErrors));
    }
}
