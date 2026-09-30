-- 운영 확인용 최소 사용자 활동 기록. 서비스 데이터와 같은 MySQL에 두어 사용자·대화와 같은 기준으로 조회한다.
-- BOUNDARY: 비밀번호·JWT·Refresh Token·내부 API 키 같은 비밀값과 질문·답변 전문은 저장하지 않는다(대화 기준 저장소는 messages).
CREATE TABLE activity_logs (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '활동 기록 식별자. 기록 순서대로 커진다.',
    user_id BIGINT UNSIGNED NULL COMMENT '활동한 사용자(users.id). 없는 계정으로 로그인 실패처럼 사용자를 특정할 수 없으면 NULL이다.',
    action VARCHAR(40) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '활동 종류. SIGNUP·LOGIN·LOGOUT·COMPANY_CREATE·COMPANY_UPDATE·CONVERSATION_CREATE·AI_QUERY·ELIGIBILITY_CHECK 중 하나다.',
    target_type VARCHAR(40) CHARACTER SET ascii COLLATE ascii_bin NULL COMMENT '활동 대상 종류(USER·COMPANY·CONVERSATION·PROGRAM). 대상이 없으면 NULL이다.',
    target_id VARCHAR(80) CHARACTER SET ascii COLLATE ascii_bin NULL COMMENT '활동 대상 식별자. 서비스 테이블 id 또는 지원사업 공고 ID(pblanc_id)를 문자로 저장한다.',
    success BOOLEAN NOT NULL COMMENT '활동 결과. 1=성공, 0=실패(로그인 실패·AI 호출 실패 등).',
    error_code VARCHAR(80) CHARACTER SET ascii COLLATE ascii_bin NULL COMMENT '실패했을 때 서비스 공통 오류 code(예: auth_invalid_credentials, ai_service_timeout). 성공이면 NULL이다.',
    metadata_json JSON NULL COMMENT '운영 확인에 필요한 최소 부가 정보(예: AI 결과 종류·공고 수, 자격 판정 상태, 로그인 실패 사유). 비밀값·입력 원문·질문과 답변 전문은 넣지 않는다.',
    created_at DATETIME(6) NOT NULL COMMENT '활동을 기록한 UTC 시각.',
    INDEX idx_activity_logs_user_time (user_id, created_at),
    INDEX idx_activity_logs_action_time (action, created_at),
    CONSTRAINT fk_activity_logs_user FOREIGN KEY (user_id) REFERENCES users(id),
    CHECK (success = 1 OR error_code IS NOT NULL)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
COMMENT='사용자 활동 기록(회원가입·로그인·로그아웃·기업정보 등록/수정·대화 생성·AI 검색·자격 판정). 운영 확인과 문제 추적용이며 수정하지 않고 쌓기만 한다.';
