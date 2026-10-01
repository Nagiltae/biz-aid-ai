# Database 규칙

MySQL은 서비스 사실과 구조화 데이터를, Qdrant는 문서 검색 metadata와 vector를 담당한다.
MongoDB는 실제 필요성 확인과 ADR 없이 도입하지 않는다. 회원·기업·대화·메시지·활동 로그·AI 흐름 상태는 MySQL에 둔다.
영구 기업정보는 companies, AI 흐름에서 사용자가 답한 임시 기업정보는 ai_workflows.state_json에만 둔다(companies 자동 반영 금지). ai_workflows의 status·current_step은 state_json에서 복사한 값이며 따로 바꾸지 않는다.

Flyway를 사용한다. 적용된 V1~Vn 수정 금지, schema 변경은 신규 Migration으로 작성한다.
Spring Boot도 공통 `migrations/`와 같은 `flyway_schema_history`를 쓴다(V6: users·refresh_tokens·companies·conversations·messages, V7: ASSISTANT 메시지 AI 결과 column, V8: activity_logs, V9: ai_workflows). 두 번째 migration 체계를 만들지 않는다.
Spring Boot의 DB 접근은 Spring Data JPA이며 일반 CRUD는 Repository 메서드로, 여러 조건이 조합되는 지원사업 검색만 QueryDSL로 작성한다. MyBatis는 쓰지 않는다.
Migration은 Git 추적하고 Test / Docs / Contract를 동기화한다.
Phase 1A 사용자 승인으로 Compose dev MySQL과 공통 `migrations/` Flyway가 도입됐다.
Python Repository는 DDL을 만들지 않는다. dev Pilot과 controlled test DB를 분리한다.
실행하지 않은 Migration을 검증 완료로 기록하지 않는다. prod 접근은 이번 범위 밖이다.

Phase 2 문서 원본 byte는 MySQL에 넣지 않는다. DB는 공고와 source field/token 관계, 공개 URL, 원본 파일명,
content-addressed 로컬 경로, format/HTTP/size/SHA-256, 성공·실패 상태와 실행 이력만 보존한다.
동일 binary dedupe가 provenance relation을 제거해서는 안 되며 V3는 기존 V1/V2를 수정하지 않고 추가한다.
Phase 2.5의 V4는 검증된 S3 region/bucket/object key/시각만 추가한다. legacy `storage_path`는 로컬 migration source로
유지하고 S3 영구 위치와 혼용하지 않는다. 전체 S3 object 검증 뒤 모든 relation metadata를 한 transaction에서 연결한다.
Phase 3의 V5는 `(source_sha256, parse_key)`별 parse 상태·provenance·S3 artifact pointer·parser identity를 MySQL에 저장한다.
DoclingDocument JSON byte는 MySQL에 넣지 않는다. PARSED만 artifact metadata를 가지며 S3 검증 전 성공 row commit을 금지한다.
같은 key는 idempotent하게 재사용하고 새 parse_key는 기존 row와 artifact를 덮어쓰지 않는다.
보관과 서비스 검색 범위는 다르다. MySQL·S3는 과거(종료) 공고까지 전부 보관하고, 서비스 검색용 Qdrant(V2, `QDRANT_COLLECTION_NAMESPACE=v2`)에는 종료가 확실한(CLOSED) 공고를 뺀 OPEN·UPCOMING·UNKNOWN 공고 문서만 적재한다.
V1 collection(`bizaid_chunks_v1_228acdd12220`)은 V1 baseline 재현용이라 수정·추가 적재하지 않는다(적재 경로는 namespace 필수). 검색 collection 전환은 코드가 아니라 설정으로 한다.
V2 적재가 끝나기 전 V1 collection으로 하는 확인은 기능 흐름 확인용이며 V2 검색 품질 평가로 쓰지 않는다.
Phase 4 chunk·vector는 MySQL에 저장하지 않는다. Qdrant index는 S3 parsed artifact와 V5 row에서 다시 만들 수 있는 파생 데이터이며 MySQL과 Qdrant는 pblanc_id·source_sha256으로만 연결한다.

## Application schema COMMENT

프로젝트 소유 application DB의 모든 신규 Table / Column은 non-empty 한국어 COMMENT가 필수다.
Table은 목적·책임·어떤 사실을 보존하는지 설명한다. Column은 비즈니스 의미와 원본 Source field를 설명한다.
Raw / Derived / Lifecycle 차이, 시간 기준·정밀도·수량 단위가 중요하면 명시하고 boolean의 true/false 의미를 구분한다.
DataGrip에서 이해 가능한 1~2문장을 기준으로 하며 이름 반복·TODO·TBD·단독 "데이터"/"값"·실제 Secret·개인정보 예시는 금지한다.

현재 검사 경계는 `biz_aid_dev` / `biz_aid_test`의 모든 BASE TABLE과 Column이다.
고정 application table 이름 목록을 두지 않으며 Flyway의 `flyway_schema_history`만 명시적으로 제외한다.
MySQL system schema와 prod는 검사 연결 대상이 아니다. 새 infra 소유 예외나 View를 도입하면 ownership과 검사 정책을 별도 Task에서 검토한다.

check-integration → check-all에서 실제 information_schema의 Table / Column COMMENT를 검사한다.
빈 값·placeholder·이름 반복·한국어 설명 부재는 실패한다. 의미의 정확성과 설명 누락은 AGY / Human Review로 확인한다.
COMMENT 추가의 MODIFY COLUMN은 기존 타입·길이·NULL/default·generated/auto increment·charset/collation·키·FK·CHECK를 보존한다.
SHOW CREATE TABLE과 information_schema를 비교해 COMMENT 외 정의 변경이 없어야 한다.

적용된 migration의 COMMENT 누락도 그 파일을 수정해서 해결하지 않는다.
예: 적용된 V3에서 누락 발견 → V3 보존 → 신규 V4로 COMMENT 추가 → migrate / validate / schema 비교.
