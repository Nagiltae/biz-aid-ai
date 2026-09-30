# 안전과 권한

작업 범위는 current-task에 명시한다. 범위 밖 기능·외부 데이터 출처·큰 기술 도입은 먼저 보고한다.
Harness 규칙 완화·삭제는 사용자의 명시적 지시와 변경 이유·AGY 검토가 필요하다.
Secret·credential(JWT_SECRET·INTERNAL_AI_API_KEY 포함)을 코드·report·log·fixture·profile 설정 파일(application-*.yml)에 기록하지 않는다. 환경변수로만 주입하고 오류 응답에 싣지 않는다.
사용자 활동 기록(activity_logs)에는 비밀번호·JWT·Refresh Token·내부 API 키와 질문·답변 전문을 넣지 않는다. 대화 내용의 기준 저장소는 messages다.
원문·실패 데이터·사용자 변경을 임의 삭제하거나 덮어쓰지 않는다.
임의 Push·Merge·force push·branch 삭제를 하지 않는다.
