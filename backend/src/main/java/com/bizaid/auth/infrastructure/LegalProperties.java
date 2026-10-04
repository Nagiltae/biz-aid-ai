package com.bizaid.auth.infrastructure;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * 현재 시행 중인 이용약관·개인정보처리방침 버전(시행일). 가입·체험 동의 기록에 이 값을 남긴다.
 * BOUNDARY: 화면(frontend/src/features/legal/legalVersions.ts)의 버전과 같아야 한다. 계약 검사가 두 값을 비교한다.
 */
@ConfigurationProperties(prefix = "bizaid.legal")
public record LegalProperties(String termsVersion, String privacyVersion) {
}
