package com.bizaid.auth;

import com.bizaid.common.ApiException;
import com.bizaid.common.ErrorCode;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Instant;
import java.util.Base64;
import java.util.HexFormat;
import java.util.Locale;
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

    public AuthService(UserRepository users, RefreshTokenRepository refreshTokens, PasswordEncoder passwordEncoder,
                       JwtTokenProvider tokenProvider, AuthProperties properties, Clock clock) {
        this.users = users;
        this.refreshTokens = refreshTokens;
        this.passwordEncoder = passwordEncoder;
        this.tokenProvider = tokenProvider;
        this.properties = properties;
        this.clock = clock;
    }

    /** 가입 직후 바로 서비스를 쓰도록 로그인과 같은 토큰을 발급한다. */
    @Transactional
    public AuthDtos.IssuedTokens signup(AuthDtos.SignupRequest request) {
        String email = normalize(request.email());
        if (users.existsByEmail(email)) {
            throw new ApiException(ErrorCode.AUTH_EMAIL_TAKEN);
        }
        User user = users.save(new User(email, passwordEncoder.encode(request.password()), request.displayName().trim(),
                clock.instant()));
        return issue(user);
    }

    @Transactional
    public AuthDtos.IssuedTokens login(AuthDtos.LoginRequest request) {
        // 이메일 없음과 비밀번호 틀림을 같은 오류로 돌려 가입 여부를 추측할 수 없게 한다.
        User user = users.findByEmail(normalize(request.email()))
                .filter(found -> passwordEncoder.matches(request.password(), found.getPasswordHash()))
                .orElseThrow(() -> new ApiException(ErrorCode.AUTH_INVALID_CREDENTIALS));
        return issue(user);
    }

    @Transactional(noRollbackFor = ApiException.class)
    public AuthDtos.IssuedTokens refresh(String rawRefreshToken) {
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
        refreshTokens.findByTokenHash(hash(rawRefreshToken)).ifPresent(token -> token.revoke(clock.instant()));
    }

    @Transactional(readOnly = true)
    public AuthDtos.UserResponse me(Long userId) {
        return users.findById(userId).map(AuthDtos.UserResponse::from)
                .orElseThrow(() -> new ApiException(ErrorCode.AUTH_REQUIRED));
    }

    private RefreshToken findStored(String rawRefreshToken) {
        if (rawRefreshToken == null || rawRefreshToken.isBlank()) {
            throw new ApiException(ErrorCode.AUTH_REFRESH_INVALID);
        }
        return refreshTokens.findByTokenHash(hash(rawRefreshToken))
                .orElseThrow(() -> new ApiException(ErrorCode.AUTH_REFRESH_INVALID));
    }

    private AuthDtos.IssuedTokens issue(User user) {
        Instant now = clock.instant();
        byte[] bytes = new byte[32];
        RANDOM.nextBytes(bytes);
        String refreshToken = Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
        refreshTokens.save(new RefreshToken(user.getId(), hash(refreshToken), now.plus(properties.jwt().refreshTokenTtl()), now));
        AuthDtos.TokenResponse body = new AuthDtos.TokenResponse(tokenProvider.createAccessToken(user),
                tokenProvider.accessTokenTtlSeconds(), AuthDtos.UserResponse.from(user));
        return new AuthDtos.IssuedTokens(body, refreshToken);
    }

    private static String normalize(String email) {
        return email.trim().toLowerCase(Locale.ROOT);
    }

    // Refresh Token은 32byte 무작위 값이라 추측이 불가능하므로 느린 비밀번호 해시가 아닌 SHA-256으로 충분하고, 조회도 해시로 바로 할 수 있다.
    static String hash(String rawToken) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(rawToken.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException(exception);
        }
    }
}
