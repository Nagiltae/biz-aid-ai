-- AI 응답(ASSISTANT) 메시지의 구조화 결과를 보존해 대화를 다시 열어도 공고 카드·답변·근거를 복원한다.
-- 기존 V6 messages 정의는 바꾸지 않고 nullable column만 추가한다. USER 메시지와 기존 row는 두 column이 NULL이다.
ALTER TABLE messages
    MODIFY COLUMN content MEDIUMTEXT NOT NULL
        COMMENT '화면에 보여 주는 메시지 본문. USER는 질문, ASSISTANT는 AI가 쓴 자연어 답변이다. 자연어 답이 없는 목록 결과(SEARCH_LIST)는 Spring이 문장을 지어내지 않도록 빈 문자열이며 결과는 ai_result_json에 있다.',
    ADD COLUMN ai_result_type VARCHAR(20) CHARACTER SET ascii COLLATE ascii_bin NULL
        COMMENT 'ASSISTANT 메시지의 AI 결과 종류. FastAPI가 정한 request_mode 값(SEARCH_LIST=지원사업 목록, DOCUMENT_QA=공고문 질문 답변)이며 USER 메시지는 NULL이다.' AFTER content,
    ADD COLUMN ai_result_json JSON NULL
        COMMENT 'FastAPI AI 결과를 Spring 응답 형식(camelCase)으로 옮긴 구조화 JSON. 공고 목록 순위·답변·공고문 근거를 FastAPI 값 그대로 보존하며 Spring이 새로 만든 값은 없다. USER 메시지는 NULL이다.' AFTER ai_result_type,
    ADD CONSTRAINT chk_messages_ai_result CHECK (
        (role = 'USER' AND ai_result_type IS NULL AND ai_result_json IS NULL)
        OR (role = 'ASSISTANT' AND ai_result_type IN ('SEARCH_LIST', 'DOCUMENT_QA') AND ai_result_json IS NOT NULL)
    );

ALTER TABLE messages
    COMMENT='대화에 속한 사용자 질문(USER)과 AI 응답(ASSISTANT) 메시지. AI 응답은 FastAPI 호출이 성공했을 때만 저장하고, 화면 복원용 구조화 결과를 ai_result_json에 둔다.';
