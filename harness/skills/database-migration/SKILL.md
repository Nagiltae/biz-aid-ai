---
name: database-migration
description: MySQL schema 변경과 신규 Flyway Migration 검증이 승인된 Task에 필요할 때 사용한다.
---

# database-migration

현재 Phase에서는 추가 workflow/reference가 필요하지 않음. 아래 본문과 연결된 Context / Rule로 작업 범위를 확인한다.

Phase 1A의 승인된 dev DB는 공통 Flyway를 사용한다.
[DB 규칙](../../rules/database-rules.md)에 따라 적용된 Migration을 보존하고 신규 번호를 확인한다.
새 Migration·관련 Repository / Contract / Test / Docs를 함께 변경하고 실제 Flyway 실행 결과를 기록한다.

모든 신규 application Table / Column에 [COMMENT 정책](../../rules/database-rules.md)을 적용한다.
Table 책임과 Column의 Source / Raw / Derived / Lifecycle·시간/단위·boolean 의미를 한국어로 설명한다.
누락이 적용 후 발견돼도 기존 파일은 수정하지 않고 다음 migration에서 보완한다.
COMMENT용 MODIFY COLUMN도 기존 정의를 보존하고 SHOW CREATE TABLE / information_schema로 COMMENT 외 변경을 확인한다.
dev/test Flyway migrate / validate와 check-integration의 실제 schema COMMENT 검사를 수행한다.
