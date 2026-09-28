# Checkpoint / Resume / Recovery

장시간 Phase 0 Task는 Agent 대화 기억에 상태를 맡기지 않는다.
API 품질 Batch는 Run metadata를 사용하고, 제한된 Document Download Gate는 아래 규칙의 실제 checkpoint를 생성한다.

## 최소 Format

`harness/workspace/checkpoints/<run_id>-<순번>.md`에 아래 YAML 또는 동등한 JSON block과 설명을 기록한다.
매 갱신은 순번을 늘려 새 파일로 보존한다. 이전 실패와 진행 증거를 덮어쓰지 않는다.
현재 Stage에서 무엇을 한 item으로 세는지 notes에 정의하고 일관되게 적용한다.

| 필드 | 타입 / 의미 |
| --- | --- |
| run_id | Task 실행 식별 문자열. 원문·Report와 연결 |
| task | 승인된 Task 이름 / current-task와 연결 |
| started_at | 최초 실행 시각, ISO 8601 + timezone |
| updated_at | 이 checkpoint 기록 시각, ISO 8601 + timezone |
| total_target | 현재 Stage의 전체 item 목표 수, 0 이상 정수 |
| completed_count | 해당 Stage에서 성공 처리가 확정된 고유 item 수 |
| failed_count | 해당 Stage에서 현재 실패 상태인 고유 item 수 |
| failed_items | 실패 목록. item_id, stage, reason, attempts, evidence 경로 / checksum |
| current_stage | 현재 작업 단계. Stage 전환 시 이전 기록을 보존하고 집계를 새로 시작 |
| last_processed_item | 마지막으로 결과를 확정한 item ID / cursor와 증거, 시작 전 null |
| next_action | 다음에 수행할 구체적인 동작, 추가 동작 없으면 null |
| resume_command | 현재 구현된 명령만 기록, 안전하게 재개할 명령이 없으면 null |
| notes | 집계 단위·입력·원문 checksum·제외 기준·미결정 사항·마지막 검증 결과 |
| status | running / blocked / completed |

failed_items는 credential·원문 내용 대신 오류 분류와 상대 경로·checksum을 담는다.
completed_count와 failed_count는 중복되지 않고 합계는 total_target을 넘지 않는다.
재시도 횟수를 실패 item 수로 세지 않는다. 재시도 성공 시 현재 집계를 옮기되 과거 기록은 보존한다.

아래는 **합성 Format 예시**이며 실제 API 수집·성공·실패 결과가 아니다.
resume_command는 이미 존재하는 로컬 checksum 검증 명령을 예시로 사용한다.
실제 파일이 준비되지 않았다면 해당 명령을 실행하지 않는다.

```yaml
run_id: format-example
task: "Phase 0 원문 무결성 확인 — 합성 예시"
started_at: "2026-09-27T10:00:00+09:00"
updated_at: "2026-09-27T10:05:00+09:00"
total_target: 2
completed_count: 1
failed_count: 1
failed_items:
  - item_id: sample-002
    stage: snapshot-integrity
    reason: checksum-mismatch
    attempts: 1
    evidence: "data/raw/sample-002/metadata.json"
current_stage: snapshot-integrity
last_processed_item: sample-002
next_action: "원문과 metadata를 대조하고 실패 이유를 확인한다"
resume_command: "python3 scripts/phase0.py verify-snapshot data/raw/sample-002/metadata.json"
notes:
  - "집계 단위는 snapshot 1개이며 API 수집률이나 Gate 판정이 아니다"
  - "실제 checkpoint에서는 각 원문의 SHA-256과 마지막 검증 결과를 추가한다"
status: blocked
```

## 생성 / 갱신 / 완료

- 생성: 장시간 실행 또는 세션 분할 Task 시작 전에 입력 범위·목표·Stage·다음 동작을 기록한다.
- 갱신: 각 item 결과를 확정하거나 batch/page를 끝냈을 때, 실패·중단·Stage 전환·Session 교체 직전에 새 순번을 쓴다.
- 확정 순서: 원문 / 결과 저장 → checksum·계약 등 해당 검증 → 성공/실패 기록 → checkpoint.
  저장 도중 중단된 item은 성공으로 세지 않고 복원 시 먼저 확인한다.
- 완료: 목표 item의 성공/실패가 모두 집계되고 결과·예외·Validation이 Final Report에 보존되며,
  재개할 동작이 없을 때 status=completed, next_action=null, resume_command=null로 기록한다.
  실패가 남았으면 Report에서 처리·보류 이유를 설명한다. Checkpoint 완료는 Gate GO가 아니다.
- 승인 대기나 재개 불가능한 명령은 status=blocked와 이유를 기록한다. 미구현 Collector 명령을 만들지 않는다.

## 새 Session / Agent의 복원

1. AGENTS → current-task → 관련 Report를 읽어 Task 승인 범위와 run_id를 확인한다.
2. 해당 run_id의 최신 유효 순번을 읽고 필요하면 이전 기록과 대조한다.
3. 원문·metadata의 경로와 checksum, 마지막 확정 item과 집계 단위를 검사한다.
4. 불완전한 마지막 item·실패 item은 재확인한다. 같은 run-id의 원문을 덮어쓰지 않는다.
5. resume_command의 존재·권한·재실행 안전성을 확인하고 next_action 범위 안에서만 재개한다.
6. 재개 결과를 새 checkpoint에 기록한다. 증거가 불일치하면 멈추고 이유를 Report에 남긴다.

완료 checkpoint도 보존하며 payload·credential은 기록하지 않는다.
이 README는 STATIC_DOCUMENTATION으로 strict 검증한다. run-specific Markdown은 GENERATED_CHECKPOINT다.
새 checkpoint는 ignore 가능하며 tracking·format·존재·Git 상태는 build 조건이 아니다. required_files 개별 등록도 하지 않는다.
하위 run 디렉터리 기록도 생성물이다. build는 생성물 내용을 읽거나 실행하지 않으며 실제 Resume는 명시적 실행에서 무결성을 확인한다.

## Document Download Gate 적용

시작·10개 Candidate 확정마다·실패·중단·다운로드 집계 완료 시 새 순번 Markdown / JSON block을 만든다.
각 원본 / metadata는 매 Candidate마다 먼저 확정하므로 Checkpoint 사이 결과도 checksum으로 복원한다.
completed_count=success_count, processed_count=success_count+failed_count이며 remaining_count=100-processed_count다.
last_processed_pblancId와 원본 source run/hash를 추가한다. 순번 기록과 기존 byte를 덮어쓰지 않는다.
다운로드 집계 완료 Checkpoint는 Report의 계산 근거이며 Task 종료 Validation / 독립 Review를 대신하지 않는다.
--resume은 성공과 확정 실패를 모두 건너뛰고 미처리 대상만 요청한다. 자동 실패 재시도는 없다.
고립 파일·checksum 불일치는 Report에 기록하고 사람의 확인 전 멈춘다.
