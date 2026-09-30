package com.bizaid.common.error;

import jakarta.servlet.RequestDispatcher;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.boot.web.servlet.error.ErrorController;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Controller에 도달하기 전에 끝난 요청(예: 보안 필터가 거부한 이상한 URL)의 오류도 같은 본문 형식으로 돌려준다.
 * Spring 기본 오류 JSON(timestamp·path 등)을 그대로 두면 React가 오류 형식을 두 가지로 처리해야 한다.
 */
@RestController
public class ApiErrorController implements ErrorController {

    @RequestMapping("/error")
    public ResponseEntity<ErrorResponse> error(HttpServletRequest request) {
        Object value = request.getAttribute(RequestDispatcher.ERROR_STATUS_CODE);
        int status = value instanceof Integer code ? code : 500;
        ErrorCode errorCode = switch (status) {
            case 401 -> ErrorCode.AUTH_REQUIRED;
            case 404 -> ErrorCode.NOT_FOUND;
            case 405 -> ErrorCode.METHOD_NOT_ALLOWED;
            default -> status >= 400 && status < 500 ? ErrorCode.MALFORMED_REQUEST : ErrorCode.INTERNAL_ERROR;
        };
        return ResponseEntity.status(status).body(ErrorResponse.of(errorCode));
    }
}
