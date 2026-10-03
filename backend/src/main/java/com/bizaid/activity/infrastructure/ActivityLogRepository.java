package com.bizaid.activity.infrastructure;

import org.springframework.data.repository.query.Param;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.jpa.repository.Modifying;
import com.bizaid.activity.domain.ActivityLog;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ActivityLogRepository extends JpaRepository<ActivityLog, Long> {

    /**
     * 회원 탈퇴: 활동 기록은 운영 통계용으로 남기되 그 사용자를 가리키는 값(user_id, 사용자 대상 id)을 지운다.
     * 대화·기업처럼 이미 지운 행의 id는 다른 사람을 가리키지 않으므로 대상 종류만 남기고 id도 비운다.
     */
    @Modifying
    @Query("update ActivityLog a set a.userId = null, a.targetId = null, "
            + "a.targetType = case when a.targetType = 'USER' then null else a.targetType end where a.userId = :userId")
    int anonymizeUser(@Param("userId") Long userId);
}
