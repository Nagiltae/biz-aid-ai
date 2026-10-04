package com.bizaid.auth.infrastructure;

import com.bizaid.auth.domain.AuthUser;
import com.bizaid.auth.domain.User;
import io.jsonwebtoken.Claims;
import io.jsonwebtoken.JwtException;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.time.Instant;
import java.util.Date;
import java.util.Optional;
import javax.crypto.SecretKey;
import org.springframework.stereotype.Component;

/**
 * Access Token(JWT) 발급·검증.
 * Access Token은 15분짜리 서명 토큰이라 서버에 저장하지 않는다. 짧게 두는 이유는 탈취돼도 피해 시간이 짧게 끝나게 하기 위해서다.
 * 오래 유지되는 로그인은 DB로 폐기할 수 있는 Refresh Token이 담당한다.
 */
@Component
public class JwtTokenProvider {

    private final SecretKey key;
    private final AuthProperties.Jwt settings;
    private final Clock clock;

    public JwtTokenProvider(AuthProperties properties, Clock clock) {
        this.settings = properties.jwt();
        String secret = settings.secret();
        // RISK: 짧은 secret은 HS256 서명을 추측 공격에 약하게 만든다. 설정 누락과 함께 시작 시점에 실패시킨다.
        if (secret == null || secret.getBytes(StandardCharsets.UTF_8).length < 32) {
            throw new IllegalStateException("JWT_SECRET must be set and at least 32 bytes");
        }
        this.key = Keys.hmacShaKeyFor(secret.getBytes(StandardCharsets.UTF_8));
        this.clock = clock;
    }

    public String createAccessToken(User user) {
        Instant now = clock.instant();
        return Jwts.builder()
                .subject(String.valueOf(user.getId()))
                .claim("email", user.getEmail())
                .claim("trial", user.isTrial())
                .issuedAt(Date.from(now))
                .expiration(Date.from(now.plus(settings.accessTokenTtl())))
                .signWith(key)
                .compact();
    }

    public long accessTokenTtlSeconds() {
        return settings.accessTokenTtl().toSeconds();
    }

    /** 서명·만료가 유효하면 사용자 정보를, 아니면 빈 값을 돌려준다. 실패 이유는 응답에 노출하지 않는다. */
    public Optional<AuthUser> parse(String token) {
        try {
            Claims claims = Jwts.parser().verifyWith(key).clock(() -> Date.from(clock.instant())).build()
                    .parseSignedClaims(token).getPayload();
            return Optional.of(new AuthUser(Long.valueOf(claims.getSubject()), claims.get("email", String.class),
                    Boolean.TRUE.equals(claims.get("trial", Boolean.class))));
        } catch (JwtException | IllegalArgumentException exception) {
            return Optional.empty();
        }
    }
}
