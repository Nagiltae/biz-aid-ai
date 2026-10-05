package com.bizaid.auth.application;

import com.bizaid.activity.application.ActivityLogService;
import com.bizaid.activity.domain.ActivityAction;
import com.bizaid.auth.domain.RefreshToken;
import com.bizaid.auth.domain.User;
import com.bizaid.auth.infrastructure.AuthProperties;
import com.bizaid.auth.infrastructure.JwtTokenProvider;
import com.bizaid.auth.infrastructure.RefreshTokenRepository;
import com.bizaid.auth.infrastructure.UserRepository;
import com.bizaid.common.error.ApiException;
import com.bizaid.common.error.ErrorCode;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Instant;
import java.util.Base64;
import java.util.HexFormat;
import java.util.Locale;
import java.util.Map;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 회원가입·로그인·토큰 재발급·로그아웃.
 * Refresh Token은 재발급할 때마다 이전 토큰을 폐기하고 새 토큰으로 바꾼다(rotation).
 * 이미 폐기된 토큰이 다시 들어오면 누군가 복사해 둔 토큰일 수 있으므로 그 사용자의 유효한 토큰을 모두 폐기한다.
 */
@Service
public class AuthService {

    private static final SecureRandom RANDOM = new SecureRandom();

    private final UserRepository users;
    private final RefreshTokenRepository refreshTokens;
    private final PasswordEncoder passwordEncoder;
    private final JwtTokenProvider tokenProvider;
    private final AuthProperties properties;
    private final Clock clock;
    private final ActivityLogService activityLog;
    private final LoginThrottleService loginThrottle;
    private final ConsentService consents;

    public AuthService(UserRepository users, RefreshTokenRepository refreshTokens, PasswordEncoder passwordEncoder,
                       JwtTokenProvider tokenProvider, AuthProperties properties, Clock clock, ActivityLogService activityLog,
                       LoginThrottleService loginThrottle, ConsentService consents) {
        this.consents = consents;
        this.users = users;
        this.refreshTokens = refreshTokens;
        this.passwordEncoder = passwordEncoder;
        this.tokenProvider = tokenProvider;
        this.properties = properties;
        this.clock = clock;
        this.activityLog = activityLog;
        this.loginThrottle = loginThrottle;
    }

    /** 가입 직후 바로 서비스를 쓰도록 로그인과 같은 토큰을 발급한다. 필수 동의(약관·개인정보)는 요청 DTO가 확인하고 여기서 버전과 시각을 기록한다. */
    @Transactional
    public IssuedTokens signup(String rawEmail, String password, String displayName) {
        String email = normalize(rawEmail);
        if (users.existsByEmail(email)) {
            activityLog.failure(ActivityAction.SIGNUP, null, null, null, ErrorCode.AUTH_EMAIL_TAKEN.code(), null);
            throw new ApiException(ErrorCode.AUTH_EMAIL_TAKEN);
        }
        User user = users.save(new User(email, passwordEncoder.encode(password), displayName.trim(), clock.instant()));
        consents.recordRequired(user.getId(), clock.instant());
        IssuedTokens tokens = issue(user);
        activityLog.success(ActivityAction.SIGNUP, user.getId(), "USER", user.getId(), null);
        return tokens;
    }

    @Transactional
    public IssuedTokens login(String email, String password, String clientIp) {
        String normalized = normalize(email);
        // BOUNDARY: 계정 또는 접속 IP가 잠겨 있으면 비밀번호를 확인하지 않는다(잠긴 동안 대입 시도가 맞는지 알려 주지 않음).
        try {
            loginThrottle.checkAllowed(normalized, clientIp);
        } catch (ApiException exception) {
            activityLog.failure(ActivityAction.LOGIN, null, null, null, exception.errorCode().code(), Map.of("reason", "locked"));
            throw exception;
        }
        // 이메일 없음과 비밀번호 틀림을 같은 오류로 돌려 가입 여부를 추측할 수 없게 한다.
        User found = users.findByEmail(normalized).orElse(null);
        if (found == null || !passwordEncoder.matches(password, found.getPasswordHash())) {
            boolean locked = loginThrottle.recordFailure(normalized, clientIp);
            // 활동 기록에는 입력한 이메일·비밀번호·IP를 남기지 않는다(비밀번호를 이메일 칸에 잘못 넣는 경우도 있다).
            activityLog.failure(ActivityAction.LOGIN, found == null ? null : found.getId(), null, null,
                    ErrorCode.AUTH_INVALID_CREDENTIALS.code(),
                    Map.of("reason", found == null ? "unknown_account" : "wrong_password", "locked", locked));
            throw new ApiException(ErrorCode.AUTH_INVALID_CREDENTIALS);
        }
        loginThrottle.recordSuccess(normalized);
        IssuedTokens tokens = issue(found);
        activityLog.success(ActivityAction.LOGIN, found.getId(), "USER", found.getId(), null);
        return tokens;
    }

    @Transactional(noRollbackFor = ApiException.class)
    public IssuedTokens refresh(String rawRefreshToken) {
        Instant now = clock.instant();
        RefreshToken stored = findStored(rawRefreshToken);
        if (stored.isRevoked()) {
            // RISK: 폐기된 토큰의 재사용은 탈취 신호다. 정상 사용자도 다시 로그인해야 하지만 공격자의 세션을 끊는 쪽을 택한다.
            refreshTokens.revokeAllActive(stored.getUserId(), now);
            throw new ApiException(ErrorCode.AUTH_REFRESH_INVALID);
        }
        if (!stored.isUsable(now)) {
            throw new ApiException(ErrorCode.AUTH_REFRESH_INVALID);
        }
        stored.revoke(now);
        User user = users.findById(stored.getUserId()).orElseThrow(() -> new ApiException(ErrorCode.AUTH_REFRESH_INVALID));
        return issue(user);
    }

    /** 쿠키가 없거나 이미 폐기된 토큰이어도 로그아웃은 성공으로 처리한다. 결과는 어떤 경우든 "로그아웃 상태"다. */
    @Transactional
    public void logout(String rawRefreshToken) {
        if (rawRefreshToken == null || rawRefreshToken.isBlank()) {
            return;
        }
        refreshTokens.findByTokenHash(hash(rawRefreshToken)).ifPresent(token -> {
            token.revoke(clock.instant());
            activityLog.success(ActivityAction.LOGOUT, token.getUserId(), "USER", token.getUserId(), null);
        });
    }

    @Transactional(readOnly = true)
    public User me(Long userId) {
        return users.findById(userId).orElseThrow(() -> new ApiException(ErrorCode.AUTH_REQUIRED));
    }

    private RefreshToken findStored(String rawRefreshToken) {
        if (rawRefreshToken == null || rawRefreshToken.isBlank()) {
            throw new ApiException(ErrorCode.AUTH_REFRESH_INVALID);
        }
        return refreshTokens.findByTokenHash(hash(rawRefreshToken))
                .orElseThrow(() -> new ApiException(ErrorCode.AUTH_REFRESH_INVALID));
    }

    /** 비밀번호를 바꾼 뒤 다른 기기 로그인을 모두 끊고 지금 사용자에게 새 토큰을 준다. */
    @Transactional
    public IssuedTokens reissueAfterPasswordChange(User user) {
        refreshTokens.revokeAllActive(user.getId(), clock.instant());
        return issue(user);
    }

    IssuedTokens issue(User user) {
        Instant now = clock.instant();
        byte[] bytes = new byte[32];
        RANDOM.nextBytes(bytes);
        String refreshToken = Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
        refreshTokens.save(new RefreshToken(user.getId(), hash(refreshToken), now.plus(properties.jwt().refreshTokenTtl()), now));
        return new IssuedTokens(user, tokenProvider.createAccessToken(user), tokenProvider.accessTokenTtlSeconds(), refreshToken);
    }

    private static String normalize(String email) {
        return email.trim().toLowerCase(Locale.ROOT);
    }

    // Refresh Token은 32byte 무작위 값이라 추측이 불가능하므로 느린 비밀번호 해시가 아닌 SHA-256으로 충분하고, 조회도 해시로 바로 할 수 있다.
    // WHY: 접속 IP counter도 기존과 같은 SHA-256 구현을 재사용한다. 원문은 저장하거나 출력하지 않는다.
    public static String hash(String rawToken) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(rawToken.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException(exception);
        }
    }
}
