-- V2-3 상태 기반 추천 흐름(LangGraph)의 요청 간 상태 저장. Spring이 소유하고 FastAPI는 이 테이블을 읽거나 쓰지 않는다.
-- 흐름 상태(State)는 JSON 한 덩어리로 저장하고, 조회·잠금에 필요한 값(status·current_step)만 일반 column으로 둔다.
CREATE TABLE ai_workflows (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT 'AI 추천 흐름(workflow) 식별자. API의 workflowId다.',
    user_id BIGINT UNSIGNED NOT NULL COMMENT '흐름을 시작한 사용자(users.id). 다른 사용자는 조회·진행할 수 없다.',
    status VARCHAR(20) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '흐름 상태. IN_PROGRESS=다음 단계 진행 가능, WAITING_FOR_USER=부족 정보 답변 대기, COMPLETED=판정 완료, FAILED=검색 실패 등으로 중단. state_json의 status와 항상 같다.',
    current_step VARCHAR(40) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '다음에 할 단계(SEARCH·EVALUATE_PROGRAM·AWAIT_ANSWERS·DONE·FAILED). state_json의 current_step과 항상 같다.',
    state_json JSON NOT NULL COMMENT 'LangGraph 흐름 상태 전체: 질문, 기업정보 snapshot, 이번 흐름의 임시 기업정보, Top 3, 공고별 판정 결과, 남은 판정 대상, 부족 정보. 문서 원문·prompt·비밀값은 넣지 않는다.',
    version BIGINT NOT NULL DEFAULT 0 COMMENT '동시 요청 방지용 낙관적 잠금 버전. 저장할 때마다 1 증가하며, 읽은 뒤 다른 요청이 먼저 바꿨으면 저장을 거부한다.',
    step_started_at DATETIME(6) NULL COMMENT '다음 단계를 실행 중인 요청이 흐름을 점유한 UTC 시각. NULL이면 실행 중인 단계가 없다. 오래된 점유(5분 초과)는 중단된 실행으로 보고 다시 점유할 수 있다.',
    created_at DATETIME(6) NOT NULL COMMENT '흐름을 시작한 UTC 시각.',
    updated_at DATETIME(6) NOT NULL COMMENT '상태가 마지막으로 저장된 UTC 시각.',
    INDEX idx_ai_workflows_user_recent (user_id, updated_at),
    CONSTRAINT fk_ai_workflows_user FOREIGN KEY (user_id) REFERENCES users(id),
    CHECK (status IN ('IN_PROGRESS', 'WAITING_FOR_USER', 'COMPLETED', 'FAILED'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
COMMENT='AI 추천 흐름(개인화 검색 → 공고별 자격 판정 → 추가 질문 → 재판정)의 요청 간 상태. 영구 기업정보는 companies, 이번 판정용 임시 정보는 state_json에 둔다.';
