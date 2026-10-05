-- WHY: 기존 V13은 적용 이력으로 보존한다. 새 사용량 key와 같은 시행일의 개정 버전을 DataGrip에서도 이해할 수 있게 COMMENT만 갱신한다.
-- BOUNDARY: type·길이·charset·collation·nullable·key·데이터는 기존 정의 그대로다.
ALTER TABLE ai_usage_counters
    MODIFY COLUMN counter_key VARCHAR(80) CHARACTER SET ascii COLLATE ascii_bin NOT NULL
        COMMENT '횟수를 세는 대상. USER:<users.id>=사용자별 AI 사용, TRIAL_POOL=체험 전체 AI 사용, SERVICE_POOL=서비스 전체 AI 사용, TRIAL_IP:<SHA-256>=접속 IP별 체험 생성, SIGNUP_IP:<SHA-256>=접속 IP별 가입 요청. IP 원문은 저장하지 않는다.',
    COMMENT='한국 날짜별 사용자·체험·서비스 AI 사용 횟수와 IP별 체험·가입 요청 횟수. 조건부 UPDATE로 상한을 지키며 AI 실패는 예약 횟수를 환불한다. 정리 작업은 7일 지난 행을 삭제한다.';

ALTER TABLE user_consents
    MODIFY COLUMN document_version VARCHAR(20) CHARACTER SET ascii COLLATE ascii_bin NOT NULL
        COMMENT '동의 당시 화면의 문서 버전. 시행일 YYYY-MM-DD와 같은 날 개정 번호(.번호)를 함께 기록한다. 서버 설정과 화면 버전은 같아야 한다.';
