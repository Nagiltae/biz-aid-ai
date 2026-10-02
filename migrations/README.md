# 공통 DB migration

Schema owner는 이 디렉터리의 **Flyway**다. Python은 DDL을 생성하지 않는다.
Phase 1A 이전에 backend와 migration 구현이 없었으므로 사용자 승인으로 공통 owner를 정했다.
향후 Spring Boot도 이 migration 계보를 사용한다. Alembic 등 별도 체계를 만들지 않는다.

`V1__structured_support_programs.sql`은 `support_programs`와 실행 이력을 생성한다.
적용된 migration은 수정하지 않고 새로운 버전으로 변경한다. Flyway `validate`로 checksum을 확인한다.
`infra/mysql/init-dev.sql`은 최초 test DB만 준비한다. `infra/dev_mysql.py`가 선택된 기존 사용자에 test DB 권한을 부여하며 application schema를 관리하지 않는다.

원본 JSON은 key 누락/null/빈 문자열/unknown field를 보존한다. 날짜 파생값과 UTC lifecycle은 별도다.
`pblanc_id`는 ASCII binary unique key다. 물리 삭제 대신 source presence를 기록한다.
개발용 `biz_aid_test`는 fixture 검증 DB이고 `biz_aid_dev`의 Pilot 데이터를 변경하지 않는다.

`V2__add_database_comments.sql`은 기존 2개 application Table / 42개 Column의 한국어 COMMENT만 추가한다.
실제 column 정의를 보존하며 Flyway 내부 테이블은 변경하지 않는다.
모든 신규 Table / Column은 [DB COMMENT 규칙](../harness/rules/database-rules.md)을 적용한다.
적용된 migration에서 설명 누락을 발견해도 수정하지 않고 다음 버전으로 보완한다.
check-integration / check-all의 실제 information_schema 검사와 V1→V2 fixture schema 비교로 검증한다.

`V3__document_source_layer.sql`은 Phase 2 실행 이력과 문서 후보 relation metadata를 추가한다.
Binary는 DB가 아닌 ignored content-addressed local storage에 두며 FK로 support_program과 run을 연결한다.
source role/field/token, URL/filename, format/HTTP/size/SHA/path, 성공·실패와 마지막 실행 action을 보존한다.
V1/V2는 수정하지 않으며 V3의 모든 Table / Column도 동일 COMMENT 정책을 적용한다.

`V4__document_s3_storage.sql`은 기존 V1/V2/V3를 보존하며 `document_sources`에 검증된 S3 위치와 검증 시각을 추가한다.
네 S3 field는 모두 NULL 또는 모두 non-NULL이어야 한다. `storage_path`는 legacy 로컬 migration source로 유지한다.
로컬 corpus 삭제나 이 호환 제약 변경은 Phase 2.5 독립 검토 이후 별도 신규 migration에서만 판단한다.

`V10__document_archive_members.sql`은 일반 ZIP 내부 파일의 경로·SHA·실제 형식·처리 결정·S3 위치를 보존한다(2026-10-02 사용자 승인 뒤 적용).
승인 전에는 Flyway가 읽지 않는 별도 폴더에 두었다. 이 폴더의 migration은 check-all의 dev 준비 단계와 Spring backend가 dev DB에 적용하기 때문이다.

`V5__document_parse_results.sql`은 `(source_sha256, parse_key)`별 parsing 상태와 parser identity를 보존한다.
PARSED 결과만 검증된 S3 DoclingDocument JSON pointer·artifact SHA·byte 크기를 가지며, 비성공 결과는 artifact metadata를 가질 수 없다.
같은 key 재실행은 row와 object를 재사용하고 새 parse_key는 기존 결과를 덮어쓰지 않고 별도 row로 남긴다.
