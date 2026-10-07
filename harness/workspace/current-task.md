# 현재 Task

## 목표 / 승인 범위

PROJECT_MASTER_GUIDE를 사용자의 프로젝트 공부·면접 준비 자료로 갱신(2026-10-07 사용자 요청).
이 문서 하나에서 서비스/기술/요청 흐름·공부할 코드·문제와 실험·선택 이유·출처 있는 수치·남은 한계·면접 답변을 이해하도록 한다. 기존 AI 인수인계 설명은 보존한다.

## 상태

문서 내용을 기존 코드·계약·실험 기록과 대조해 갱신하고, 링크·형식·관련 격리 Harness 검증 후 사용자 검토 대기. 실제 검사 결과는 Final Report에 기록한다. 이전 CI 수정과 Task 원문은 새 Report에 보존한다.

## Read First

AGENTS → workflow/git-policy → feature-development Skill → safety/file-boundaries → PROJECT_MASTER_GUIDE → AI 개선 전/후 문서 → 표/검색/모델/장애 실험 Report → 해당 production code·계약·테스트.

## Acceptance / Safety

- 가이드 안에 학습 순서·기술 역할·대표 흐름·실험 과정·수치 출처/환경/한계·면접 답변을 작성한다. 없는 숫자나 본인 기여·미실행 성과를 만들지 않는다.
- PROJECT_MASTER_GUIDE·current-task·Registry.report·Changelog와 Generated 보고서만 변경한다. 기존 CI 수정의 PNG 등록을 보존한다. 앱·테스트·규칙·Compose·README·이미지 변경 0.
- 실제 .env/.env.dev/.env.prod·AWS 인증 파일 열람/출력 0. 실제 LLM/모델 재평가·운영 서버/AWS 접속·서비스 중지/시작 0.
- git add/commit/push 0. 기존 사용자 변경을 stage하거나 되돌리지 않으며 개발자가 AGY 승인 기록을 만들지 않는다.

## Validation

숫자와 설정/측정 구분·출처 확인 → 코드 경로/문서 링크 → 기존 형식/문법/주석/Git 검사 → 실제 설정 없는 임시 저장소에서 관련 Harness 검사 → Generated Report.
원본 저장소 check-all/setup/check-harness·Integration은 실제 환경 파일을 읽을 수 있어 NOT_RUN. 앱 빌드·실제 AI 평가·원격 CI·운영 검증·AGY 검토는 NOT_RUN/PENDING. 실행하지 않은 검사를 PASS로 기록하지 않는다.

## Expected Report

[Final Report](reports/development/2026-10-07-master-guide-study-and-interview.md)
