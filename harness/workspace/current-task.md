# 현재 Task

## 목표 / 승인 범위

README용 프로젝트 설명 이미지 생성(2026-10-07 사용자 승인). 한 이미지에는 한 주제만 담고 이미지들만으로 서비스·구조·문서 처리·AI 판단·실험·운영을 이해할 수 있게 만든다.
기존 디자인과 공개 코드/문서/보고서 근거를 사용해 6장의 PNG를 docs/images/에 저장하고 README에서 연결한다. 실제 화면 캡처 자리는 별도로 보존한다.

## 상태

6개 이미지 생성·직접 확인·저장·README 연결 및 PNG 검사 보완 완료, 가능한 정적 검사와 관련 테스트 통과. 사용자 검토 대기. 이전 Task/Git 근거를 Report/Artifact에 보존했다. 전체 gate·운영 확인·AGY 검토는 실행하지 않았다.

## Read First

AGENTS → Registry → workflow/git-policy → PROJECT_MASTER_GUIDE → README → 개선 전/후 측정·배포 문서 → 이미지 생성 Skill.
feature-development Skill과 safety/file-boundaries를 따른다.

## Acceptance / Safety

- PNG마다 한 주제, 큰 한국어 글씨·짧은 문장·일관된 스타일. 실제 정보/실측하지 않은 수치·가짜 화면을 추가하지 않는다.
- docs/images PNG·README 연결·Task/Registry/Changelog와 PNG 형식 검사만 변경한다. 앱·Compose·Dockerfile·계약·DB·Rule 변경 0.
- 실제 .env/.env.dev/.env.prod·AWS 인증 파일 열람/출력 0. 실제 앱 모델 평가·빌드/push·서버/AWS 접속·commit/push 0.
- 기존 staged/unstaged 사용자 작업 보존. 새 이미지 입력만 명시 경로로 stage한다. 개발자가 AGY 승인 기록을 만들지 않는다.

## Validation

이미지 직접 확인 → 내용·수치/날짜·관계·글자 확인 → README 링크·PNG 파일 형식·Registry → 기존 형식/문법/주석/Git 검사 → Report.
기존 전체 gate/Compose는 실제 환경 파일을 읽을 수 있어 NOT_RUN. 앱/DB/브라우저·운영·실제 LLM 재평가·AGY 검토는 NOT_RUN/PENDING.

## Expected Report

[Final Report](reports/development/2026-10-07-readme-infographics.md)
