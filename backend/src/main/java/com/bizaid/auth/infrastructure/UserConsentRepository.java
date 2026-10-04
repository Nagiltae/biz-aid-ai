package com.bizaid.auth.infrastructure;

import com.bizaid.auth.domain.UserConsent;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface UserConsentRepository extends JpaRepository<UserConsent, Long> {

    List<UserConsent> findByUserIdOrderByDocumentType(Long userId);

    @Modifying
    @Query("delete from UserConsent c where c.userId = :userId")
    int deleteAllByUser(@Param("userId") Long userId);
}
