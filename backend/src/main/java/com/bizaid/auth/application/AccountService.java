package com.bizaid.auth.application;

import com.bizaid.activity.application.ActivityLogService;
import com.bizaid.activity.domain.ActivityAction;
import com.bizaid.activity.infrastructure.ActivityLogRepository;
import com.bizaid.ai.infrastructure.AiWorkflowRepository;
import com.bizaid.auth.domain.User;
import com.bizaid.auth.infrastructure.RefreshTokenRepository;
import com.bizaid.auth.infrastructure.UserRepository;
import com.bizaid.common.error.ApiException;
import com.bizaid.common.error.ErrorCode;
import com.bizaid.company.infrastructure.CompanyRepository;
import com.bizaid.conversation.infrastructure.ConversationRepository;
import com.bizaid.conversation.infrastructure.MessageRepository;
import java.time.Clock;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 계정 관리: 회원 탈퇴·비밀번호 변경. 둘 다 현재 비밀번호를 다시 확인한다.
 *
 * <p>탈퇴 정책(2026-10-04 사용자 결정): 회원·기업정보·대화(메시지 포함)·추천 흐름(ai_workflows)·Refresh Token은 즉시 지운다.
 * 활동 기록(activity_logs)은 운영 통계로 남기되 user_id·대상 id를 지워 그 사람을 가리킬 수 없게 한다.
 * 기존 Access Token은 JwtAuthenticationFilter가 사용자 행이 없으면 인증하지 않아 즉시 무효가 된다.
 */
@Service
public class AccountService {

    private final UserRepository users;
    private final RefreshTokenRepository refreshTokens;
    private final CompanyRepository companies;
    private final ConversationRepository conversations;
    private final MessageRepository messages;
    private final AiWorkflowRepository workflows;
    private final ActivityLogRepository activityLogs;
    private final ActivityLogService activityLog;
    private final PasswordEncoder passwordEncoder;
    private final AuthService authService;
    private final Clock clock;

    public AccountService(UserRepository users, RefreshTokenRepository refreshTokens, CompanyRepository companies,
                          ConversationRepository conversations, MessageRepository messages, AiWorkflowRepository workflows,
                          ActivityLogRepository activityLogs, ActivityLogService activityLog, PasswordEncoder passwordEncoder,
                          AuthService authService, Clock clock) {
        this.users = users;
        this.refreshTokens = refreshTokens;
        this.companies = companies;
        this.conversations = conversations;
        this.messages = messages;
        this.workflows = workflows;
        this.activityLogs = activityLogs;
        this.activityLog = activityLog;
        this.passwordEncoder = passwordEncoder;
        this.authService = authService;
        this.clock = clock;
    }

    @Transactional
    public void withdraw(Long userId, String password) {
        User user = verified(userId, password);
        // BOUNDARY: 외래키 순서대로 자식 행부터 지운다(messages → conversations, 나머지는 users만 참조).
        messages.deleteAllByUser(userId);
        conversations.deleteAllByUser(userId);
        workflows.deleteAllByUser(userId);
        companies.deleteAllByUser(userId);
        refreshTokens.deleteAllByUser(userId);
        activityLogs.anonymizeUser(userId);
        users.delete(user);
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
        if (password == null || !passwordEncoder.matches(password, user.getPasswordHash())) {
            throw new ApiException(ErrorCode.AUTH_PASSWORD_MISMATCH);
        }
        return user;
    }
}
