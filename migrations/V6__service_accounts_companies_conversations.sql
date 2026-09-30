-- 서비스 V1(React + Spring Boot)의 회원·인증·기업정보·대화 테이블. 공통 Flyway 계보를 그대로 이어서 추가한다.
-- 지원사업(support_programs)은 데이터 파이프라인이 소유하므로 여기서 복제하거나 변경하지 않는다.
-- 시각 column은 기존 V1~V5와 같이 DATETIME(6) UTC로 저장한다.
CREATE TABLE users (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '서비스 사용자 내부 식별자. 기업정보·대화·Refresh Token이 이 값으로 사용자를 가리킨다.',
    email VARCHAR(255) NOT NULL COMMENT '로그인 ID로 쓰는 이메일 주소. 소문자로 정규화해 저장하며 서비스 전체에서 중복될 수 없다.',
    password_hash VARCHAR(100) NOT NULL COMMENT 'Spring Security PasswordEncoder(BCrypt)로 만든 비밀번호 해시. 평문 비밀번호는 어디에도 저장하지 않는다.',
    display_name VARCHAR(50) NOT NULL COMMENT '화면 상단 등에 보여 주는 사용자 이름(닉네임). 로그인에는 쓰지 않는다.',
    created_at DATETIME(6) NOT NULL COMMENT '회원가입이 완료된 UTC 시각.',
    updated_at DATETIME(6) NOT NULL COMMENT '사용자 정보가 마지막으로 바뀐 UTC 시각.',
    UNIQUE KEY uq_users_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
COMMENT='BizAid 서비스에 가입한 사용자 계정. 로그인 인증의 기준이며 관리자·권한 구분은 V1 범위 밖이다.';

CREATE TABLE refresh_tokens (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT 'Refresh Token 발급 기록 식별자.',
    user_id BIGINT UNSIGNED NOT NULL COMMENT '이 Refresh Token을 발급받은 사용자(users.id).',
    token_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT 'Refresh Token 원문의 SHA-256 hex. 원문은 브라우저 HttpOnly Cookie에만 있고 DB가 유출돼도 토큰으로 쓸 수 없게 해시만 저장한다.',
    expires_at DATETIME(6) NOT NULL COMMENT '이 Refresh Token을 더 이상 재발급에 쓸 수 없게 되는 UTC 만료 시각(발급 후 14일).',
    revoked_at DATETIME(6) NULL COMMENT '재발급으로 새 토큰에 교체(rotation)되었거나 로그아웃으로 폐기된 UTC 시각. NULL이면 아직 유효한 토큰이다.',
    created_at DATETIME(6) NOT NULL COMMENT 'Refresh Token을 발급한 UTC 시각.',
    UNIQUE KEY uq_refresh_tokens_hash (token_hash),
    INDEX idx_refresh_tokens_user (user_id, revoked_at),
    CONSTRAINT fk_refresh_tokens_user FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
COMMENT='JWT Access Token 재발급에 쓰는 Refresh Token의 해시와 수명 기록. 재발급 때마다 이전 토큰을 폐기하고 새 토큰을 발급한다(rotation). 폐기 row는 삭제하지 않고 revoked_at으로 남긴다.';

CREATE TABLE companies (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '기업정보 식별자.',
    user_id BIGINT UNSIGNED NOT NULL COMMENT '이 기업정보를 등록한 사용자(users.id). V1은 사용자 1명당 기업 1개라서 UNIQUE다.',
    company_name VARCHAR(100) NOT NULL COMMENT '사용자가 입력한 회사 상호. 화면 표시와 자격 판정 요청의 company_name에 쓴다.',
    business_entity_type VARCHAR(10) NULL COMMENT '사업자 형태. 개인사업자 또는 법인이며 공고의 지원 대상 구분과 비교한다. NULL은 아직 입력하지 않음.',
    company_size VARCHAR(30) NULL COMMENT '기업 규모 구분(예: 소상공인, 중소기업, 중견기업). 사용자가 스스로 입력한 값이며 확인서 검증은 하지 않는다.',
    region VARCHAR(100) NULL COMMENT '사업장 소재지(예: 경기도 광명시). 지역 한정 공고의 자격 비교에 쓴다.',
    industry VARCHAR(100) NULL COMMENT '주 업종 이름 또는 표준산업분류 코드. 업종 제한 공고의 자격 비교에 쓴다.',
    business_start_date DATE NULL COMMENT '개업일(사업자등록상 개업 연월일). 업력(개월)은 저장하지 않고 판정 기준일에 이 날짜로 계산한다.',
    business_status VARCHAR(10) NULL COMMENT '현재 영업 상태. 영업중·휴업·폐업 중 하나이며 휴·폐업 제외 조건 비교에 쓴다.',
    employee_count INT UNSIGNED NULL COMMENT '상시근로자 수(명). 고용 규모 요건 비교에 쓴다.',
    annual_revenue_krw BIGINT UNSIGNED NULL COMMENT '최근 1년 연 매출액. 단위는 원(KRW)이다.',
    venture_certified BOOLEAN NULL COMMENT '벤처기업 확인 여부. 1=확인받음, 0=확인받지 않음, NULL=입력하지 않음.',
    research_institute BOOLEAN NULL COMMENT '기업부설연구소(또는 연구개발전담부서) 보유 여부. 1=보유, 0=미보유, NULL=입력하지 않음.',
    exporter BOOLEAN NULL COMMENT '수출 실적이 있는 수출기업인지 여부. 1=수출기업, 0=아님, NULL=입력하지 않음.',
    created_at DATETIME(6) NOT NULL COMMENT '기업정보를 처음 등록한 UTC 시각.',
    updated_at DATETIME(6) NOT NULL COMMENT '기업정보를 마지막으로 수정한 UTC 시각.',
    UNIQUE KEY uq_companies_user (user_id),
    CONSTRAINT fk_companies_user FOREIGN KEY (user_id) REFERENCES users(id),
    CHECK (business_entity_type IS NULL OR business_entity_type IN ('개인사업자', '법인')),
    CHECK (business_status IS NULL OR business_status IN ('영업중', '휴업', '폐업'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
COMMENT='사용자가 등록한 기업의 오래 유지되는 기본정보. 지원 자격 판정 때 CompanyProfileSnapshot으로 변환한다. 신용점수·체납·공고별 추가 사실처럼 민감하거나 자주 바뀌는 정보는 저장하지 않고 판정 요청 때만 받는다.';

CREATE TABLE conversations (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '대화 식별자.',
    user_id BIGINT UNSIGNED NOT NULL COMMENT '이 대화를 만든 사용자(users.id). 다른 사용자의 대화는 조회할 수 없다.',
    title VARCHAR(200) NOT NULL COMMENT '대화 목록에 보여 주는 제목. 화면은 첫 질문의 앞부분을 넣고 비어 있으면 "새 대화"로 저장한다.',
    created_at DATETIME(6) NOT NULL COMMENT '대화를 시작한 UTC 시각.',
    updated_at DATETIME(6) NOT NULL COMMENT '마지막 메시지가 저장된 UTC 시각. 대화 목록을 최근 순으로 정렬하는 기준이다.',
    INDEX idx_conversations_user_recent (user_id, updated_at),
    CONSTRAINT fk_conversations_user FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
COMMENT='사용자와 AI 지원사업 검색·질문의 대화 묶음. V1은 메시지 저장만 하며 AI 응답 생성은 FastAPI 연결 단계에서 붙는다.';

CREATE TABLE messages (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY COMMENT '메시지 식별자. 같은 대화 안에서 저장 순서대로 커진다.',
    conversation_id BIGINT UNSIGNED NOT NULL COMMENT '이 메시지가 속한 대화(conversations.id).',
    role VARCHAR(20) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '메시지 작성 주체. USER=사용자 질문, ASSISTANT=AI 응답.',
    content MEDIUMTEXT NOT NULL COMMENT '화면에 보여 주는 메시지 본문 텍스트.',
    created_at DATETIME(6) NOT NULL COMMENT '메시지를 저장한 UTC 시각.',
    INDEX idx_messages_conversation (conversation_id, id),
    CONSTRAINT fk_messages_conversation FOREIGN KEY (conversation_id) REFERENCES conversations(id),
    CHECK (role IN ('USER', 'ASSISTANT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
COMMENT='대화에 속한 사용자 질문과 AI 응답 메시지. AI 근거(citation) 같은 부가 정보 column은 FastAPI 연결 단계에서 실제 응답 형태를 보고 신규 migration으로 추가한다.';
