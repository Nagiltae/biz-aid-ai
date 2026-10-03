package com.bizaid.auth.presentation;

import com.bizaid.auth.application.AuthService;
import com.bizaid.auth.domain.AuthUser;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import org.springframework.http.HttpHeaders;
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
    private final RefreshCookies cookies;

    public AuthController(AuthService authService, RefreshCookies cookies) {
        this.authService = authService;
        this.cookies = cookies;
    }

    @PostMapping("/signup")
    public ResponseEntity<AuthDtos.TokenResponse> signup(@Valid @RequestBody AuthDtos.SignupRequest request) {
        return cookies.withRefreshCookie(authService.signup(request.email(), request.password(), request.displayName()));
    }

    @PostMapping("/login")
    public ResponseEntity<AuthDtos.TokenResponse> login(@Valid @RequestBody AuthDtos.LoginRequest request,
                                                        HttpServletRequest httpRequest) {
        // 접속 IP는 Tomcat RemoteIpValve가 신뢰하는 내부 proxy(nginx)의 X-Forwarded-For로 정한 값이다.
        return cookies.withRefreshCookie(authService.login(request.email(), request.password(), httpRequest.getRemoteAddr()));
    }

    /** 새로고침 등으로 메모리의 Access Token을 잃었거나 만료됐을 때 Cookie의 Refresh Token으로 다시 발급한다. */
    @PostMapping("/refresh")
    public ResponseEntity<AuthDtos.TokenResponse> refresh(@CookieValue(name = "${bizaid.refresh-cookie.name}", required = false)
                                                          String refreshToken) {
        return cookies.withRefreshCookie(authService.refresh(refreshToken));
    }

    @PostMapping("/logout")
    public ResponseEntity<Void> logout(@CookieValue(name = "${bizaid.refresh-cookie.name}", required = false) String refreshToken) {
        authService.logout(refreshToken);
        return ResponseEntity.noContent().header(HttpHeaders.SET_COOKIE, cookies.cleared()).build();
    }

    @GetMapping("/me")
    public AuthDtos.UserResponse me(@AuthenticationPrincipal AuthUser user) {
        return AuthDtos.UserResponse.from(authService.me(user.id()));
    }
}
