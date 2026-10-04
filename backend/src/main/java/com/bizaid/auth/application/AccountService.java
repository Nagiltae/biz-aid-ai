package com.bizaid.auth.application;

import com.bizaid.activity.application.ActivityLogService;
import com.bizaid.activity.domain.ActivityAction;
import com.bizaid.auth.domain.User;
import com.bizaid.auth.infrastructure.UserRepository;
import com.bizaid.common.error.ApiException;
import com.bizaid.common.error.ErrorCode;
import java.time.Clock;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 계정 관리: 회원 탈퇴·비밀번호 변경. 둘 다 현재 비밀번호를 다시 확인한다.
 *
 * <p>탈퇴 정책(2026-10-04 사용자 결정): 회원·기업정보·대화(메시지 포함)·추천 흐름(ai_workflows)·Refresh Token은 즉시 지운다.
 * 활동 기록(activity_logs)은 운영 통계로 남기되 user_id·대상 id를 지워 그 사람을 가리킬 수 없게 한다(UserDataPurger).
 * 기존 Access Token은 JwtAuthenticationFilter가 사용자 행이 없으면 인증하지 않아 즉시 무효가 된다.
 */
@Service
public class AccountService {

    private final UserRepository users;
    private final UserDataPurger purger;
    private final ActivityLogService activityLog;
    private final PasswordEncoder passwordEncoder;
    private final AuthService authService;
    private final Clock clock;

    public AccountService(UserRepository users, UserDataPurger purger, ActivityLogService activityLog, PasswordEncoder passwordEncoder,
                          AuthService authService, Clock clock) {
        this.users = users;
        this.purger = purger;
        this.activityLog = activityLog;
        this.passwordEncoder = passwordEncoder;
        this.authService = authService;
        this.clock = clock;
    }

    @Transactional
    public void withdraw(Long userId, String password) {
        verified(userId, password);
        purger.purge(userId);
        // 탈퇴 기록은 사용자를 가리키지 않는 형태로만 남긴다(커밋 뒤 기록).
        activityLog.success(ActivityAction.ACCOUNT_DELETE, null, null, null, null);
    }

    @Transactional
    public IssuedTokens changePassword(Long userId, String currentPassword, String newPassword) {
        User user = verified(userId, currentPassword);
        user.changePassword(passwordEncoder.encode(newPassword), clock.instant());
        activityLog.success(ActivityAction.PASSWORD_CHANGE, userId, "USER", userId, null);
        return authService.reissueAfterPasswordChange(user);
    }

    private User verified(Long userId, String password) {
        User user = users.findById(userId).orElseThrow(() -> new ApiException(ErrorCode.AUTH_REQUIRED));
        // BOUNDARY: Controller의 토큰 확인과 별개로 DB의 계정 종류로 한 번 더 막는다(체험 계정은 탈퇴·비밀번호 변경 불가).
        if (user.isTrial()) {
            throw new ApiException(ErrorCode.TRIAL_ACCOUNT_RESTRICTED);
        }
        if (password == null || !passwordEncoder.matches(password, user.getPasswordHash())) {
            throw new ApiException(ErrorCode.AUTH_PASSWORD_MISMATCH);
        }
        return user;
    }
}
