package com.bizaid.auth.infrastructure;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

/** JWT·Refresh Cookie 설정. secret은 환경변수 JWT_SECRET으로만 주입하며 코드와 Git에 두지 않는다. */
@ConfigurationProperties(prefix = "bizaid")
public record AuthProperties(Jwt jwt, RefreshCookie refreshCookie) {

    public record Jwt(String secret, Duration accessTokenTtl, Duration refreshTokenTtl) {
    }

    public record RefreshCookie(String name, String path, boolean secure) {
    }
}
