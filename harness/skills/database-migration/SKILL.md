---
name: database-migration
description: MySQL schema 변경과 신규 Flyway Migration 검증이 승인된 Task에 필요할 때 사용한다.
---

# database-migration

현재 Phase에서는 추가 workflow/reference가 필요하지 않음. 아래 본문과 연결된 Context / Rule로 작업 범위를 확인한다.

현재 DB와 Flyway 환경은 미구현이다. 이번 Task에서 Migration을 생성하지 않는다.
향후 적용 시 [DB 규칙](../../rules/database-rules.md)에 따라 적용된 Migration을 보존하고 신규 번호를 확인한다.
새 Migration·관련 Repository / Contract / Test / Docs를 함께 변경하고 실제 Flyway 실행 결과를 기록한다.
