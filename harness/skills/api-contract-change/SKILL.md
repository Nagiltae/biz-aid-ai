---
name: api-contract-change
description: 로컬 Phase 0 기록 또는 승인된 서비스 경계의 계약을 변경할 때 사용한다.
---

# api-contract-change

현재 Phase에서는 추가 workflow/reference가 필요하지 않음. 아래 본문과 연결된 Context / Rule로 작업 범위를 확인한다.

[Contracts](../../../contracts/README.md)에서 활성 계약과 미확정 upstream을 구분한다.
실제 입력 근거 없이 field / type / error를 추정하지 않는다.
변경된 producer·consumer·실패 fixture를 함께 수정하고 check-contract 및 관련 integration을 실행한다.
현재 제품 API 계약을 만드는 Task로 확대하지 않는다.
