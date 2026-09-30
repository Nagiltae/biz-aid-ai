package com.bizaid.common.error;

/** 서비스 계층이 던지는 예상된 업무 오류. GlobalExceptionHandler가 ErrorCode의 HTTP 상태와 응답 본문으로 바꾼다. */
public class ApiException extends RuntimeException {

    private final ErrorCode errorCode;

    public ApiException(ErrorCode errorCode) {
        super(errorCode.code());
        this.errorCode = errorCode;
    }

    public ErrorCode errorCode() {
        return errorCode;
    }
}
