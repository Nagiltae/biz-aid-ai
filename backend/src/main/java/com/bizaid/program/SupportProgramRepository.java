package com.bizaid.program;

import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.Repository;

/**
 * support_programs 조회 전용 Repository. save·delete가 없는 Repository를 상속해 쓰기 경로 자체를 만들지 않는다.
 * 단순 조회는 Spring Data JPA 메서드로, 여러 조건이 조합되는 목록 검색은 QueryDSL(SupportProgramQueryRepository)로 한다.
 */
public interface SupportProgramRepository extends Repository<SupportProgram, Long>, SupportProgramQueryRepository {

    Optional<SupportProgram> findByPblancIdAndSourceActiveTrueAndSourceDeletedFalse(String pblancId);

    @Query("select distinct p.category from SupportProgram p where p.sourceActive = true and p.sourceDeleted = false"
            + " and p.category is not null order by p.category")
    List<String> findActiveCategories();

    @Query("select distinct p.target from SupportProgram p where p.sourceActive = true and p.sourceDeleted = false"
            + " and p.target is not null order by p.target")
    List<String> findActiveTargets();

    @Query("select distinct p.jurisdictionName from SupportProgram p where p.sourceActive = true and p.sourceDeleted = false"
            + " and p.jurisdictionName is not null order by p.jurisdictionName")
    List<String> findActiveJurisdictions();
}
