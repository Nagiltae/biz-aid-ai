ALTER TABLE document_sources
    ADD COLUMN s3_region VARCHAR(32)
        CHARACTER SET ascii COLLATE ascii_bin
    NULL
        COMMENT '원본 binary를 저장한 AWS S3 리전. S3 이관 완료 전에는 NULL이며 현재 dev 버킷의 실제 리전을 기록한다.'
        AFTER storage_path,

    ADD COLUMN s3_bucket_name VARCHAR(255)
        CHARACTER SET ascii COLLATE ascii_bin
        NULL
        COMMENT '원본 binary를 저장한 AWS S3 버킷 이름. S3 이관 및 무결성 검증 완료 전에는 NULL이다.'
        AFTER s3_region,

    ADD COLUMN s3_object_key VARCHAR(1024)
        CHARACTER SET ascii COLLATE ascii_bin
        NULL
        COMMENT 'content SHA-256 기반 AWS S3 object key. 동일 content relation은 같은 object key를 공유할 수 있다.'
        AFTER s3_bucket_name,

    ADD COLUMN s3_verified_at DATETIME(6)
        NULL
        COMMENT 'S3 object의 byte 크기와 SHA-256 checksum을 최종 검증한 UTC 시각. 검증 전에는 NULL이다.'
        AFTER s3_object_key,

    ADD INDEX idx_document_s3_object (
        s3_bucket_name,
        s3_object_key
    ),

    ADD CONSTRAINT chk_document_s3_metadata
        CHECK (
            (
                s3_region IS NULL
                AND s3_bucket_name IS NULL
                AND s3_object_key IS NULL
                AND s3_verified_at IS NULL
            )
            OR
            (
                s3_region IS NOT NULL
                AND s3_bucket_name IS NOT NULL
                AND s3_object_key IS NOT NULL
                AND s3_verified_at IS NOT NULL
            )
        );

ALTER TABLE document_sources
    COMMENT =
    '기업마당 공고의 문서 후보 URL·원본 field 관계와 다운로드·형식·checksum·로컬 이관 경로 및 검증된 S3 저장 위치를 보존한다. Binary 자체는 저장하지 않는다.';
