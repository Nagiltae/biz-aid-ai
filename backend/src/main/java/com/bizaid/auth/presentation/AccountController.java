package com.bizaid.auth.presentation;

import com.bizaid.auth.application.AccountService;
import com.bizaid.auth.domain.AuthUser;
import jakarta.validation.Valid;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** 로그인한 본인 계정 관리(탈퇴·비밀번호 변경). 경로에 사용자 id를 받지 않고 Access Token의 사용자만 다룬다. */
@RestController
@RequestMapping("/api/account")
public class AccountController {

    private final AccountService accountService;
    private final RefreshCookies cookies;

    public AccountController(AccountService accountService, RefreshCookies cookies) {
        this.accountService = accountService;
        this.cookies = cookies;
    }

    /** 회원 탈퇴. 성공하면 Refresh Cookie도 지운다(브라우저에 남은 Cookie로 재발급되지 않게). */
    @PostMapping("/withdraw")
    public ResponseEntity<Void> withdraw(@AuthenticationPrincipal AuthUser user, @Valid @RequestBody AuthDtos.WithdrawRequest request) {
        accountService.withdraw(user.id(), request.password());
        return ResponseEntity.noContent().header(HttpHeaders.SET_COOKIE, cookies.cleared()).build();
    }

    /** 비밀번호 변경. 다른 기기 로그인을 끊고 지금 화면에는 새 토큰을 준다. */
    @PutMapping("/password")
    public ResponseEntity<AuthDtos.TokenResponse> changePassword(@AuthenticationPrincipal AuthUser user,
                                                                 @Valid @RequestBody AuthDtos.PasswordChangeRequest request) {
        return cookies.withRefreshCookie(accountService.changePassword(user.id(), request.currentPassword(), request.newPassword()));
    }
}
