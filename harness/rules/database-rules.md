# Database 규칙

MySQL은 서비스 사실과 구조화 데이터를, Qdrant는 문서 검색 metadata와 vector를 담당한다.
MongoDB는 실제 필요성 확인과 ADR 없이 도입하지 않는다.

Flyway를 사용한다. 적용된 V1~Vn 수정 금지, schema 변경은 신규 Migration으로 작성한다.
Migration은 Git 추적하고 Test / Docs / Contract를 동기화한다.
현재 DB·Migration·Flyway 실행 환경은 없다. 실행하지 않은 Migration을 검증 완료로 기록하지 않는다.
