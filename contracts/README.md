# Boundary Contracts

현재 활성 계약은 **로컬 Phase 0 기록**만 대상으로 한다.

- [Raw snapshot](schemas/raw-snapshot.contract.json): byte 보존 metadata.
- [Phase 0 report](schemas/phase0-report.contract.json): 측정 상태·분모·증거·판단 기록.
- [외부 API 준비](external-api/README.md): 실제 upstream 계약을 만들기 위한 증거 목록.
- [Frontend / Backend 경계](frontend-backend/README.md), [Backend / AI 경계](backend-ai/README.md): 미구현.

*.contract.json은 이 프로젝트의 로컬 계약 설정이며 JSON Schema 표준을 구현한 파일이 아니다.
scripts/phase0.py가 엄격한 key / type / 상태 / 의미 검증을 수행한다.
Rate와 주요 필드 Null 비율은 0..1, 확장자 분포는 파일 건수로 기록한다.
분모·표본·제외 기준의 실제 적합성은 보고서 증거와 Human review로 확인한다.
새 field는 계약·도구·테스트·문서를 함께 변경한다.
미확인 외부 Request / Response를 이 계약에서 추정하지 않는다.
현재 도구 계약은 Gate pending만 허용한다. 실제 Gate 최종 GO / DROP은
측정 후 Markdown 보고서와 사용자 검토로 기록하며 기계 기록 확장은 별도 계약 변경이다.

## Gate 판단 계약 확장 절차

현재 gate_decisions=["pending"]을 유지한다. AGY Harness Review 완료는 Data Gate GO가 아니다.

1. 승인된 별도 Phase 0 Task에서 실제 측정을 완료하고 분자·분모·표본·예외·미측정 항목을 기록한다.
2. 원문 checksum, 다운로드 / Parsing 결과, API 대비 추가정보, RAG 가치의 Evidence를 검토한다.
3. 사용자가 측정 결과와 판단 근거를 Human Review하고 계약 변경 범위 및 기록할 판단을 승인한다.
4. 별도 Contract 변경 Task를 current-task에 정의한다. Codex는 승인된 범위만 구현한다.
5. gate_decisions 확장과 근거·검토자 필드·미측정 처리·기존 pending 기록 호환성을 함께 정의한다.
6. go/drop의 정상 기록 및 미측정·근거 없음·승인 없음의 거부 Tests, 관련 Docs를 수정한다.
7. check-contract, 관련 check-integration, check-harness, check-all을 실제 실행한다.
8. 변경 이유·독립 Evidence·사용자 판단·Validation 결과를 Report / Changelog에 기록하고 Diff로 검토한다.

이 절차의 측정과 판단은 이번 Task에서 수행하지 않는다.
Codex는 자동으로 GO/DROP을 결정하거나 숫자 임계값 통과만으로 승인 상태를 생성할 수 없다.
계약 확장은 사람의 판단을 기록할 방법을 만드는 것이며 그 자체가 Gate 통과를 뜻하지 않는다.
