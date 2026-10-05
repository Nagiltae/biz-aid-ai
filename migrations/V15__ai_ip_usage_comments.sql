-- WHY: V1~V14 적용 이력은 보존한다. 계정10/IP30 사용 제한의 새 key 의미를 COMMENT에 기록한다.
-- BOUNDARY: 기존 type·길이·NULL·charset·collation·index·데이터는 변경하지 않는다.
ALTER TABLE ai_usage_counters
    MODIFY COLUMN counter_key VARCHAR(80) CHARACTER SET ascii COLLATE ascii_bin NOT NULL
        COMMENT '횟수를 세는 대상. USER:<users.id>=계정별 AI 사용, AI_IP:<SHA-256>=같은 접속 IP의 AI 합산 사용, TRIAL_POOL=체험 전체 AI 사용, SERVICE_POOL=서비스 전체 AI 사용, TRIAL_IP:<SHA-256>=IP별 체험 생성, SIGNUP_IP:<SHA-256>=IP별 가입 요청. 원문 IP는 저장하지 않는다.',
    COMMENT='한국 날짜별 계정·접속 IP·체험·서비스 AI 사용과 IP별 체험·가입 요청 횟수. 조건부 UPDATE로 각 상한을 지키고 거절·AI 실패는 이번 요청의 예약만 환불한다. 한국 날짜 기준 7일 된 행부터 정리한다.';
