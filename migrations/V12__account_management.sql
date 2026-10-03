-- 묶음3 서비스 관리(2026-10-04 사용자 승인): 로그인 시도 제한 상태 저장, 활동 기록 COMMENT 갱신(IMP-022).
-- BOUNDARY: 이메일·IP 원문은 저장하지 않고 SHA-256(종류:값)만 둔다. 잠금 판단에 원문이 필요 없기 때문이다.
CREATE TABLE login_throttles (
    throttle_key CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL PRIMARY KEY COMMENT '제한 대상 식별 hash. SHA-256("ACCOUNT:" + 정규화 이메일) 또는 SHA-256("IP:" + 접속 IP)이며 원문은 저장하지 않는다.',
    key_type VARCHAR(10) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '제한 기준 종류. ACCOUNT=로그인 시도한 계정(이메일), IP=요청을 보낸 접속 주소.',
    failure_count INT UNSIGNED NOT NULL COMMENT '마지막 성공·잠금 해제 이후 연속 로그인 실패 횟수. 기준 횟수(5회)에 닿으면 잠그고 0으로 되돌린다.',
    locked_until DATETIME(6) NULL COMMENT '로그인을 받지 않는 끝 UTC 시각. NULL이거나 지난 시각이면 잠금이 아니다.',
    last_failure_at DATETIME(6) NOT NULL COMMENT '마지막 로그인 실패를 기록한 UTC 시각. 오래된 행 정리 기준이다.',
    INDEX idx_login_throttles_last_failure (last_failure_at),
    CONSTRAINT chk_login_throttles_type CHECK (key_type IN ('ACCOUNT', 'IP'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
COMMENT='로그인 시도 제한 상태. 계정·접속 IP별 연속 실패 횟수와 잠금 끝 시각만 보존하며 이메일·IP 원문과 비밀번호는 저장하지 않는다.';

ALTER TABLE activity_logs
    MODIFY COLUMN action VARCHAR(40) CHARACTER SET ascii COLLATE ascii_bin NOT NULL
        COMMENT '활동 종류. SIGNUP·LOGIN·LOGOUT·ACCOUNT_DELETE·PASSWORD_CHANGE·COMPANY_CREATE·COMPANY_UPDATE·CONVERSATION_CREATE·CONVERSATION_DELETE·AI_QUERY·ELIGIBILITY_CHECK 중 하나다.',
    MODIFY COLUMN user_id BIGINT UNSIGNED NULL
        COMMENT '활동한 사용자(users.id). 없는 계정으로 로그인 실패처럼 사용자를 특정할 수 없거나 회원 탈퇴로 식별 정보를 지운 기록은 NULL이다.',
    MODIFY COLUMN target_type VARCHAR(40) CHARACTER SET ascii COLLATE ascii_bin NULL
        COMMENT '활동 대상 종류(USER·COMPANY·CONVERSATION·PROGRAM·WORKFLOW). 대상이 없거나 회원 탈퇴로 지운 사용자 대상이면 NULL이다.';
