package com.bizaid.auth.application;

import com.bizaid.auth.domain.UserConsent;
import com.bizaid.auth.infrastructure.LegalProperties;
import com.bizaid.auth.infrastructure.UserConsentRepository;
import java.time.Instant;
import java.util.List;
import org.springframework.stereotype.Service;

/** 필수 문서 동의 기록. 호출한 쪽 트랜잭션(가입·체험 시작) 안에서 사용자 행과 함께 저장된다. */
@Service
public class ConsentService {

    private final UserConsentRepository consents;
    private final LegalProperties legal;

    public ConsentService(UserConsentRepository consents, LegalProperties legal) {
        this.consents = consents;
        this.legal = legal;
    }

    public void recordRequired(Long userId, Instant agreedAt) {
        consents.saveAll(List.of(new UserConsent(userId, UserConsent.TERMS, legal.termsVersion(), agreedAt),
                new UserConsent(userId, UserConsent.PRIVACY, legal.privacyVersion(), agreedAt)));
    }
}
