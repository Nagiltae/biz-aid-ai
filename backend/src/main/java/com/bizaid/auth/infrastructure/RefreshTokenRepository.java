package com.bizaid.auth.infrastructure;

import com.bizaid.auth.domain.RefreshToken;
import java.time.Instant;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface RefreshTokenRepository extends JpaRepository<RefreshToken, Long> {

    Optional<RefreshToken> findByTokenHash(String tokenHash);

    @Modifying
    @Query("update RefreshToken t set t.revokedAt = :now where t.userId = :userId and t.revokedAt is null")
    int revokeAllActive(@Param("userId") Long userId, @Param("now") Instant now);

    @Modifying
    @Query("delete from RefreshToken t where t.userId = :userId")
    int deleteAllByUser(@Param("userId") Long userId);

    /** IMP-016: 만료 또는 폐기 시각이 기준 시각보다 오래된 토큰만 지운다. 최근 폐기 기록은 재사용(탈취) 탐지에 남긴다. */
    @Modifying
    @Query("delete from RefreshToken t where t.expiresAt < :before or (t.revokedAt is not null and t.revokedAt < :before)")
    int deleteExpiredOrRevokedBefore(@Param("before") Instant before);
}
