package com.bizaid.auth.infrastructure;

import com.bizaid.auth.domain.LoginThrottle;
import java.time.Instant;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface LoginThrottleRepository extends JpaRepository<LoginThrottle, String> {

    /** 잠금이 끝났고 마지막 실패가 오래된 행만 지운다(정리 스케줄러). */
    @Modifying
    @Query("delete from LoginThrottle t where t.lastFailureAt < :before and (t.lockedUntil is null or t.lockedUntil < :before)")
    int deleteIdleBefore(@Param("before") Instant before);
}
