# Current Task — 기업정보 필수와 내 기업정보 화면 개편

## Goal / Context

2026-10-02 사용자 요구: 로그인 뒤 기업정보가 없으면 바로 등록 화면으로 보내고, 기업정보가 있어야 다른 기능을 쓰게 한다. 기업 규모는 선택 상자로 바꾼다. 내 기업정보는 등록돼 있으면 보기 화면과 [수정] 버튼으로 보여 주고, 메뉴는 "이름님" 오른쪽으로 옮긴다.
사용자 결정: 지원사업 목록·상세(`/programs`)는 기업정보 없이도 공개, 기업 규모 선택지는 소상공인·중소기업·중견기업·모름, 서버(대화·AI 검색 API)도 같은 규칙으로 막음, 예전 자유 입력 값은 다음 수정 때 다시 고름.
DB 스키마·migration, 인증 방식, AI 로직은 범위가 아니다.

## Read First

[AGENTS](../../AGENTS.md) → [파일 경계](../rules/file-boundaries.md) → [화면 API](../../contracts/frontend-backend/README.md).

## Scope / Acceptance

1. 로그인·가입 직후 기업정보가 없으면 `/company` 등록 화면, 있으면 원래 화면으로 간다.
2. 기업정보가 없으면 `/ai`·`/recommend`는 화면(메뉴 잠금·주소 접근)과 서버(`company_not_registered`)에서 막힌다. `/programs`는 열려 있다.
3. 기업 규모는 선택 상자이고 서버도 같은 허용값만 받는다.
4. 등록된 기업정보는 보기 화면, [수정] → 저장·취소 뒤 보기 화면. 내 기업정보 메뉴는 계정 영역에 있다.
5. React·Spring 테스트, 실제 화면 확인, check-all이 통과한다.
AGY 독립 Review / 사용자 검토는 pending이다.

## Validation / Reports

[Final Report](reports/development/2026-10-02-company-required.md). 마지막에 `./scripts/check-all.sh`를 1회 실행한다.
