package com.bizaid.auth.presentation;

import com.bizaid.auth.application.IssuedTokens;
import com.bizaid.auth.infrastructure.AuthProperties;
import java.time.Duration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseCookie;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;

/** Refresh Token Cookie를 만들고 지우는 HTTP 처리. 인증·계정 컨트롤러가 같은 규칙을 쓴다. */
@Component
public class RefreshCookies {

    private final AuthProperties properties;

    public RefreshCookies(AuthProperties properties) {
        this.properties = properties;
    }

    public ResponseEntity<AuthDtos.TokenResponse> withRefreshCookie(IssuedTokens tokens) {
        ResponseCookie cookie = cookie(tokens.refreshToken(), properties.jwt().refreshTokenTtl());
        AuthDtos.TokenResponse body = new AuthDtos.TokenResponse(tokens.accessToken(), tokens.expiresIn(),
                AuthDtos.UserResponse.from(tokens.user()));
        return ResponseEntity.ok().header(HttpHeaders.SET_COOKIE, cookie.toString()).body(body);
    }

    public String cleared() {
        return cookie("", Duration.ZERO).toString();
    }

    // HttpOnly: JS(XSS)가 읽을 수 없다. SameSite=Strict + Path=/api/auth: 다른 사이트 요청과 일반 API 요청에는 실리지 않는다.
    private ResponseCookie cookie(String value, Duration maxAge) {
        AuthProperties.RefreshCookie settings = properties.refreshCookie();
        return ResponseCookie.from(settings.name(), value).httpOnly(true).secure(settings.secure()).sameSite("Strict")
                .path(settings.path()).maxAge(maxAge).build();
    }
}
