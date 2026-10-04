package com.bizaid.auth.infrastructure;

import com.bizaid.auth.domain.AccountType;
import com.bizaid.auth.domain.User;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface UserRepository extends JpaRepository<User, Long> {

    Optional<User> findByEmail(String email);

    boolean existsByEmail(String email);

    /** 정리 대상 체험 계정(생성 시각이 기준보다 이른 것). */
    List<User> findByAccountTypeAndCreatedAtBefore(AccountType accountType, Instant before);
}
