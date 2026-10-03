package com.bizaid.ai.infrastructure;

import java.time.Instant;
import java.util.Collection;
import java.util.List;
import org.springframework.data.repository.query.Param;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.jpa.repository.Modifying;
import com.bizaid.ai.domain.AiWorkflow;
import org.springframework.data.jpa.repository.JpaRepository;

public interface AiWorkflowRepository extends JpaRepository<AiWorkflow, Long> {

    @Modifying
    @Query("delete from AiWorkflow w where w.userId = :userId")
    int deleteAllByUser(@Param("userId") Long userId);

    /** 지난 맞춤 추천 목록(최근 순, 최대 20건). */
    List<AiWorkflow> findTop20ByUserIdOrderByUpdatedAtDescIdDesc(Long userId);

    /** IMP-021: 단계를 점유한 채 기준 시각보다 오래된 흐름(실행 중 서버가 중단된 경우). */
    List<AiWorkflow> findByStepStartedAtBefore(Instant before);

    /** IMP-021: 진행 중(답변 대기 포함)인데 기준 시각 이후 한 번도 바뀌지 않은 흐름. */
    List<AiWorkflow> findByStatusInAndUpdatedAtBefore(Collection<String> statuses, Instant before);

    /** IMP-021: 보관 기간이 지난 끝난 흐름(완료·실패)만 지운다. 진행 중 흐름은 지우지 않는다. */
    @Modifying
    @Query("delete from AiWorkflow w where w.status in ('COMPLETED', 'FAILED') and w.updatedAt < :before")
    int deleteFinishedBefore(@Param("before") Instant before);
}
