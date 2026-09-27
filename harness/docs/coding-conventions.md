# Coding conventions

현재 실행 코드는 Python 표준 라이브러리와 Bash 진입점이다.
UTF-8, LF, 파일 끝 newline, trailing whitespace 금지를 적용한다.
JSON 계약은 2칸 들여쓰기와 유일한 key를 사용한다. Python은 4칸 들여쓰기다.
공유 검증은 scripts/lib/validate.py, Phase 0 동작은 scripts/phase0.py에 둔다.

[주석 정책](../rules/code-comment-policy.md)을 따른다.
원문 byte를 정규화하지 않는다. 날짜·비율·측정 여부를 추정하지 않는다.
형식이 잘못된 비어 있지 않은 원문도 보존하고 syntax invalid 상태로 구분한다.
표준 입력값 검증 실패는 명시적인 오류와 0이 아닌 종료 코드로 나타낸다.
출력 파일은 덮어쓰지 않는다. 실패 원문은 임의 삭제하지 않는다.

React / Java / FastAPI의 formatter·lint tool은 해당 코드 도입 시 결정한다.
현재 범용 format 검사는 Black / ESLint / Checkstyle 실행 결과를 뜻하지 않는다.
