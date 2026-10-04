-- 묶음5-1 공개 서비스 기능(2026-10-04 사용자 승인): 체험 계정 구분, 약관 동의 기록, 하루 AI 사용 횟수.
-- BOUNDARY: 기존 V1~V12는 수정하지 않는다. 기존 회원은 account_type 기본값 MEMBER로 그대로 쓴다.
ALTER TABLE users
    ADD COLUMN account_type VARCHAR(10) CHARACTER SET ascii COLLATE ascii_bin NOT NULL DEFAULT 'MEMBER'
        COMMENT '계정 종류. MEMBER=회원가입한 일반 회원, TRIAL=체험하기로 만든 임시 계정(생성 24시간 뒤 정리 작업이 데이터와 함께 삭제).' AFTER display_name,
    ADD INDEX idx_users_type_created (account_type, created_at),
    ADD CONSTRAINT chk_users_account_type CHECK (account_type IN ('MEMBER', 'TRIAL'));

CREATE TABLE user_consents (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '동의 기록 식별자.',
    user_id BIGINT UNSIGNED NOT NULL COMMENT '동의한 사용자(users.id). 회원 탈퇴·체험 계정 정리 때 함께 삭제한다.',
    document_type VARCHAR(20) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '동의한 문서 종류. TERMS=이용약관, PRIVACY=개인정보처리방침.',
    document_version VARCHAR(20) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '동의 당시 화면에 보여 준 문서 버전(시행일 형식, 예: 2026-10-04). 서버 설정의 현재 버전을 기록한다.',
    agreed_at DATETIME(6) NOT NULL COMMENT '사용자가 동의한 UTC 시각(회원가입 또는 체험하기 요청을 처리한 시각).',
    UNIQUE KEY uq_user_consents_document (user_id, document_type, document_version),
    CONSTRAINT fk_user_consents_user FOREIGN KEY (user_id) REFERENCES users(id),
    CONSTRAINT chk_user_consents_type CHECK (document_type IN ('TERMS', 'PRIVACY'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
COMMENT='이용약관·개인정보처리방침 필수 동의 기록. 어떤 버전의 문서에 언제 동의했는지만 보존하고 문서 본문은 저장하지 않는다.';

CREATE TABLE ai_usage_counters (
    counter_key VARCHAR(80) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '횟수를 세는 대상. USER:<users.id>=사용자별 AI 사용, TRIAL_POOL=체험 계정 전체 합산 AI 사용, TRIAL_IP:<SHA-256>=접속 IP별 체험 계정 생성(IP 원문은 저장하지 않음).',
    usage_date DATE NOT NULL COMMENT '횟수를 센 한국 날짜(Asia/Seoul). 자정이 지나면 새 날짜 행으로 다시 0부터 센다.',
    used_count INT UNSIGNED NOT NULL COMMENT '그 날짜에 사용한 횟수. 상한을 넘지 않을 때만 DB에서 원자적으로 1씩 늘리고 AI 호출이 서버 오류로 실패하면 1 되돌린다.',
    updated_at DATETIME(6) NOT NULL COMMENT '횟수가 마지막으로 바뀐 UTC 시각.',
    PRIMARY KEY (counter_key, usage_date),
    INDEX idx_ai_usage_counters_date (usage_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
COMMENT='하루 AI 사용 횟수와 체험 계정 생성 횟수. AI 검색 질문·맞춤 추천 시작·단일 자격 판정 1회를 1로 센다. 정리 작업이 7일 지난 날짜 행을 삭제한다.';

ALTER TABLE activity_logs
    MODIFY COLUMN action VARCHAR(40) CHARACTER SET ascii COLLATE ascii_bin NOT NULL
        COMMENT '활동 종류. SIGNUP·TRIAL_START·LOGIN·LOGOUT·ACCOUNT_DELETE·PASSWORD_CHANGE·COMPANY_CREATE·COMPANY_UPDATE·CONVERSATION_CREATE·CONVERSATION_DELETE·AI_QUERY·ELIGIBILITY_CHECK 중 하나다.';
