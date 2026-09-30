package com.bizaid.auth;

import jakarta.validation.Valid;
import java.time.Duration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseCookie;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.CookieValue;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** 인증 API. Refresh Token Cookie를 쓰고 지우는 HTTP 처리만 여기서 하고 판단은 AuthService가 한다. */
@RestController
@RequestMapping("/api/auth")
public class AuthController {

    private final AuthService authService;
    private final AuthProperties properties;

    public AuthController(AuthService authService, AuthProperties properties) {
        this.authService = authService;
        this.properties = properties;
    }

    @PostMapping("/signup")
    public ResponseEntity<AuthDtos.TokenResponse> signup(@Valid @RequestBody AuthDtos.SignupRequest request) {
        return withRefreshCookie(authService.signup(request));
    }

    @PostMapping("/login")
    public ResponseEntity<AuthDtos.TokenResponse> login(@Valid @RequestBody AuthDtos.LoginRequest request) {
        return withRefreshCookie(authService.login(request));
    }

    /** 새로고침 등으로 메모리의 Access Token을 잃었거나 만료됐을 때 Cookie의 Refresh Token으로 다시 발급한다. */
    @PostMapping("/refresh")
    public ResponseEntity<AuthDtos.TokenResponse> refresh(@CookieValue(name = "${bizaid.refresh-cookie.name}", required = false)
                                                          String refreshToken) {
        return withRefreshCookie(authService.refresh(refreshToken));
    }

    @PostMapping("/logout")
    public ResponseEntity<Void> logout(@CookieValue(name = "${bizaid.refresh-cookie.name}", required = false) String refreshToken) {
        authService.logout(refreshToken);
        return ResponseEntity.noContent().header(HttpHeaders.SET_COOKIE, cookie("", Duration.ZERO).toString()).build();
    }

    @GetMapping("/me")
    public AuthDtos.UserResponse me(@AuthenticationPrincipal AuthUser user) {
        return authService.me(user.id());
    }

    private ResponseEntity<AuthDtos.TokenResponse> withRefreshCookie(AuthDtos.IssuedTokens tokens) {
        ResponseCookie cookie = cookie(tokens.refreshToken(), properties.jwt().refreshTokenTtl());
        return ResponseEntity.ok().header(HttpHeaders.SET_COOKIE, cookie.toString()).body(tokens.body());
    }

    // HttpOnly: JS(XSS)가 읽을 수 없다. SameSite=Strict + Path=/api/auth: 다른 사이트 요청과 일반 API 요청에는 실리지 않는다.
    private ResponseCookie cookie(String value, Duration maxAge) {
        AuthProperties.RefreshCookie settings = properties.refreshCookie();
        return ResponseCookie.from(settings.name(), value).httpOnly(true).secure(settings.secure()).sameSite("Strict")
                .path(settings.path()).maxAge(maxAge).build();
    }
}
