CREATE TABLE document_parse_results (
    source_sha256 CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT 'Parser 입력 원본 문서 byte의 SHA-256. document_sources.content_sha256과 연결하는 원본 식별자다.',
    parse_key CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '원본 SHA·route·adapter·normalizer·parser/config/model identity로 계산한 결정론적 parsing 실행 키.',
    detected_format VARCHAR(10) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '원본 byte signature로 판정한 PDF/HWP/HWPX 등 format. 파일명 확장자와 구분한다.',
    route VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '해당 결과를 만든 production parsing route 식별자.',
    parse_status VARCHAR(24) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT 'Parsing 결과 상태. PARSED만 검증된 S3 DoclingDocument JSON artifact를 가진다.',
    artifact_s3_region VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NULL COMMENT 'Parsed DoclingDocument JSON을 영구 저장한 AWS S3 리전. 비성공 결과는 NULL이다.',
    artifact_s3_bucket_name VARCHAR(255) CHARACTER SET ascii COLLATE ascii_bin NULL COMMENT 'Parsed DoclingDocument JSON을 영구 저장한 AWS S3 버킷 이름. 비성공 결과는 NULL이다.',
    artifact_s3_object_key VARCHAR(1024) CHARACTER SET ascii COLLATE ascii_bin NULL COMMENT 'source_sha256와 parse_key로 주소화한 immutable DoclingDocument JSON S3 object key. 비성공 결과는 NULL이다.',
    artifact_sha256 CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL COMMENT '결정론적으로 직렬화한 DoclingDocument JSON byte의 SHA-256. S3 readback 검증값이다.',
    artifact_byte_size BIGINT UNSIGNED NULL COMMENT '결정론적 DoclingDocument JSON artifact의 실제 byte 크기. 단위는 byte다.',
    artifact_verified_at DATETIME(6) NULL COMMENT 'S3 object의 크기·checksum·실제 byte readback을 마지막으로 확인한 UTC 시각.',
    parser_identity_json JSON NOT NULL COMMENT 'parse_key 계산에 사용한 route·adapter·normalizer·parser/config/model/converter 버전 identity 원문.',
    warnings_json JSON NOT NULL COMMENT 'ParseResult warning code별 발생 횟수. 성공 상태에서도 품질 경고를 보존한다.',
    failure_code VARCHAR(255) CHARACTER SET ascii COLLATE ascii_bin NULL COMMENT '비성공 parsing의 구체 실패 코드. PARSED이면 NULL이다.',
    text_chars BIGINT UNSIGNED NOT NULL COMMENT '최종 DoclingDocument에서 공백을 제외해 측정한 글자 수. Artifact가 없는 결과는 관찰된 값을 저장한다.',
    unit_count INT UNSIGNED NOT NULL COMMENT 'Parser가 처리한 page 또는 section 단위 수. Route별 ParseResult 의미를 그대로 보존한다.',
    derivation_json JSON NULL COMMENT 'HWP→PDF 등 변환 route의 중간 format SHA·크기·converter identity metadata. 중간 binary는 저장하지 않는다.',
    ocr_json JSON NULL COMMENT 'OCR engine identity, 실제 OCR page와 결과 부족 page metadata. OCR 미사용 결과는 NULL이다.',
    parsed_at DATETIME(6) NOT NULL COMMENT '해당 source_sha256와 parse_key 결과를 MySQL에 최초 확정하거나 비성공 상태를 갱신한 UTC 시각.',
    PRIMARY KEY (source_sha256, parse_key),
    UNIQUE KEY uq_parse_artifact_s3 (artifact_s3_bucket_name, artifact_s3_object_key),
    INDEX idx_parse_status (parse_status, detected_format),
    CHECK (parse_status IN ('PARSED', 'EMPTY_TEXT', 'OCR_REQUIRED', 'ENCRYPTED', 'REJECTED_UNSAFE', 'CONVERSION_FAILED', 'PARSE_FAILED', 'UNSUPPORTED_FORMAT', 'ROUTE_NOT_ENABLED')),
    CHECK (
        (parse_status = 'PARSED'
            AND artifact_s3_region IS NOT NULL AND artifact_s3_bucket_name IS NOT NULL
            AND artifact_s3_object_key IS NOT NULL AND artifact_sha256 IS NOT NULL
            AND artifact_byte_size > 0 AND artifact_verified_at IS NOT NULL AND failure_code IS NULL)
        OR
        (parse_status <> 'PARSED'
            AND artifact_s3_region IS NULL AND artifact_s3_bucket_name IS NULL
            AND artifact_s3_object_key IS NULL AND artifact_sha256 IS NULL
            AND artifact_byte_size IS NULL AND artifact_verified_at IS NULL)
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
COMMENT='원본 문서 SHA와 parse_key별 Parsing 상태, parser identity 및 검증된 S3 DoclingDocument JSON 위치를 저장한다. Parsed binary 자체는 저장하지 않는다.';
