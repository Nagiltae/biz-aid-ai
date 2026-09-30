# 설명성 주석

새 설명성 주석은 한글로 작성한다. WHY / BOUNDARY / EXCEPTION / RISK를 설명한다.
동작을 번역한 주석, 의미 없는 주석 수 채우기를 금지한다.
shebang과 도구의 machine directive는 설명성 주석이 아니다.

핵심 비즈니스 로직과 설계 경계(계층 책임·보안·외부 연결 지점)에는 한국어로 "무엇을, 왜" 하는지 남긴다.
코드만 읽어도 분명한 한 줄 동작에는 주석을 달지 않는다. 코드 식별자는 영어를 유지한다.
DB table / column COMMENT는 [DB 규칙](database-rules.md)에 따라 한국어 의미를 명확히 쓴다.

check-comments는 현재 Python 주석·docstring, Bash 전체 줄 주석, Java·TypeScript(TSX)의 `//`·`/* */` 주석, CSS `/* */` 주석을 검사한다.
Bash inline comment나 다른 언어를 도입하면 lexer와 검증 범위를 함께 확장한다.
핵심 로직의 이유가 충분한지, 누락이 있는지는 AGY / 사용자 검토로 확인한다.

## 사람이 읽는 문서

설계·보고·Harness 문서는 한국어 설명을 우선한다. 전문용어는 처음 쓸 때 "한글 뜻(영문 용어)"로 쓰고 [용어집](../docs/glossary-ko.md)의 표현을 따른다.
코드 식별자·API field·Contract enum·파일 경로·기술 제품명은 번역하거나 바꾸지 않는다.
validator·test가 검사하는 문구(예: 경로 문자열, Skill 이름, anchor 제목)는 번역 때문에 지우거나 바꾸지 않고, 필요하면 한글 설명을 덧붙인다.
[PROJECT_MASTER_GUIDE](../../PROJECT_MASTER_GUIDE.md)는 주요 기능·설계·의사결정을 완료할 때 함께 갱신한다.
