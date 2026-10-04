package com.bizaid.auth.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;

/** 이용약관·개인정보처리방침 동의 기록. 어떤 버전에 언제 동의했는지만 남기고 문서 본문은 저장하지 않는다. */
@Entity
@Table(name = "user_consents")
public class UserConsent {

    public static final String TERMS = "TERMS";
    public static final String PRIVACY = "PRIVACY";

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "user_id", nullable = false)
    private Long userId;

    @Column(name = "document_type", nullable = false, length = 20)
    private String documentType;

    @Column(name = "document_version", nullable = false, length = 20)
    private String documentVersion;

    @Column(name = "agreed_at", nullable = false)
    private Instant agreedAt;

    protected UserConsent() {
    }

    public UserConsent(Long userId, String documentType, String documentVersion, Instant agreedAt) {
        this.userId = userId;
        this.documentType = documentType;
        this.documentVersion = documentVersion;
        this.agreedAt = agreedAt;
    }

    public String getDocumentType() {
        return documentType;
    }

    public String getDocumentVersion() {
        return documentVersion;
    }

    public Instant getAgreedAt() {
        return agreedAt;
    }
}
