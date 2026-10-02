CREATE TABLE document_archive_members (
    member_key CHAR(64) CHARACTER SET ascii COLLATE ascii_bin PRIMARY KEY COMMENT '압축 원본 SHA-256과 내부 파일 경로 원래 byte로 계산한 결정론적 SHA-256 관계 키. 같은 압축의 같은 항목은 다시 실행해도 같은 키다.',
    archive_source_sha256 CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '내부 파일을 담은 일반 압축 첨부의 content SHA-256. document_sources.content_sha256과 연결하며 공고 relation은 이 압축 첨부에서 물려받는다.',
    archive_depth TINYINT UNSIGNED NOT NULL COMMENT '첨부 압축에서 몇 단계 안쪽 항목인지 나타내는 깊이. 깊이 1만 펼치므로 현재 기록은 모두 1이며 압축 안 압축은 풀지 않는다.',
    parent_member_provenance JSON NULL COMMENT '깊이 2 이상 항목일 때 바깥 내부 파일들의 member_key·경로 목록. 깊이 1 항목은 바깥 내부 파일이 없어 NULL이다.',
    member_index INT UNSIGNED NOT NULL COMMENT '압축 central directory에서 0부터 센 항목 순서. 원래 압축 안 순서를 재현할 때 쓴다.',
    member_path_raw VARBINARY(1024) NOT NULL COMMENT '압축에 기록된 내부 파일 경로의 원래 byte. 이름 해석에 실패해도 원래 경로를 잃지 않도록 항상 보존한다.',
    member_path VARCHAR(1024) NULL COMMENT '사람이 읽는 내부 파일 경로. UTF-8 플래그가 있으면 UTF-8, 없으면 CP949로 해석하며 해석에 실패하면 NULL이다.',
    member_path_encoding VARCHAR(12) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '내부 파일 경로 해석 방식 UTF8_FLAG/CP949/RAW_BYTES. RAW_BYTES는 해석에 실패해 member_path_raw만 원래 이름으로 믿을 수 있다는 뜻이다.',
    member_byte_size BIGINT UNSIGNED NOT NULL COMMENT '압축 directory에 기록된 내부 파일의 해제 크기. 단위는 byte이며 읽은 byte 수와 같을 때만 SHA를 기록한다.',
    member_sha256 CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL COMMENT '압축을 푼 내부 파일 byte의 SHA-256. 파싱 입력과 S3 object key의 기준이며 읽기에 실패한 항목은 NULL이다.',
    member_detected_format VARCHAR(10) CHARACTER SET ascii COLLATE ascii_bin NULL COMMENT '내부 파일 byte signature로 판별한 실제 형식(PDF/HWP/HWPX/DOCX/PNG 등). 확장자를 믿지 않으며 읽기에 실패한 항목은 NULL이다.',
    processing_status VARCHAR(20) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '내부 파일 처리 결정 STORED/DUPLICATE_SOURCE/EXCLUDED/FAILED. STORED만 이 표를 근거로 파싱 대상이 되고 DUPLICATE_SOURCE는 같은 SHA의 단독 첨부와 연결만 남긴다.',
    status_reason VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL COMMENT '처리 결정의 계약 등록 사유 코드(예: nested_archive, intentionally_excluded_format, same_sha_as_attachment). STORED는 NULL이다.',
    s3_region VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NULL COMMENT 'STORED 내부 파일 byte를 저장한 AWS S3 리전. 저장·검증 전이거나 STORED가 아니면 NULL이다.',
    s3_bucket_name VARCHAR(255) CHARACTER SET ascii COLLATE ascii_bin NULL COMMENT 'STORED 내부 파일 byte를 저장한 AWS S3 버킷 이름. 기존 첨부 원본과 같은 버킷을 쓴다.',
    s3_object_key VARCHAR(1024) CHARACTER SET ascii COLLATE ascii_bin NULL COMMENT '내부 파일 SHA-256 기반 AWS S3 object key. 기존 첨부 원본과 같은 prefix·규칙이라 같은 byte는 같은 object를 공유한다.',
    s3_verified_at DATETIME(6) NULL COMMENT 'S3 object의 byte 크기와 SHA-256 checksum을 확인한 UTC 시각. 확인 전이거나 STORED가 아니면 NULL이다.',
    extraction_run_id VARCHAR(80) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '이 내부 파일 행을 처음 기록한 압축 펼치기 실행 ID. 실행 결과 파일과 연결하는 감사용 값이다.',
    recorded_at DATETIME(6) NOT NULL COMMENT '이 내부 파일 행을 처음 기록한 UTC 시각. 마이크로초 정밀도의 시간대 없는 DATETIME에 UTC를 저장한다.',
    INDEX idx_archive_member_archive (archive_source_sha256),
    INDEX idx_archive_member_sha (member_sha256),
    INDEX idx_archive_member_status (processing_status, status_reason),
    CONSTRAINT chk_archive_member_status CHECK (processing_status IN ('STORED', 'DUPLICATE_SOURCE', 'EXCLUDED', 'FAILED')),
    CONSTRAINT chk_archive_member_encoding CHECK (member_path_encoding IN ('UTF8_FLAG', 'CP949', 'RAW_BYTES')),
    CONSTRAINT chk_archive_member_depth CHECK ((archive_depth = 1 AND parent_member_provenance IS NULL)
        OR (archive_depth > 1 AND parent_member_provenance IS NOT NULL)),
    CONSTRAINT chk_archive_member_path CHECK ((member_path_encoding = 'RAW_BYTES' AND member_path IS NULL)
        OR (member_path_encoding <> 'RAW_BYTES' AND member_path IS NOT NULL)),
    CONSTRAINT chk_archive_member_read CHECK ((processing_status = 'FAILED' AND member_sha256 IS NULL AND member_detected_format IS NULL)
        OR (processing_status <> 'FAILED' AND member_sha256 IS NOT NULL AND member_detected_format IS NOT NULL)),
    CONSTRAINT chk_archive_member_reason CHECK ((processing_status = 'STORED' AND status_reason IS NULL)
        OR (processing_status <> 'STORED' AND status_reason IS NOT NULL)),
    CONSTRAINT chk_archive_member_s3 CHECK ((processing_status = 'STORED' AND s3_region IS NOT NULL AND s3_bucket_name IS NOT NULL
            AND s3_object_key IS NOT NULL AND s3_verified_at IS NOT NULL)
        OR (processing_status <> 'STORED' AND s3_region IS NULL AND s3_bucket_name IS NULL
            AND s3_object_key IS NULL AND s3_verified_at IS NULL))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
COMMENT='일반 압축 첨부 안 내부 파일의 경로·SHA·실제 형식·처리 결정·S3 위치를 보존한다. 공고 relation은 압축 첨부의 document_sources 행에서 물려받고 binary는 저장하지 않는다.';
