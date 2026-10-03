package com.bizaid.company.infrastructure;

import org.springframework.data.repository.query.Param;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.jpa.repository.Modifying;
import com.bizaid.company.domain.Company;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CompanyRepository extends JpaRepository<Company, Long> {

    Optional<Company> findByUserId(Long userId);

    boolean existsByUserId(Long userId);

    @Modifying
    @Query("delete from Company c where c.userId = :userId")
    int deleteAllByUser(@Param("userId") Long userId);
}
