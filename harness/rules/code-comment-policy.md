# 설명성 주석

새 설명성 주석은 한글로 작성한다. WHY / BOUNDARY / EXCEPTION / RISK를 설명한다.
동작을 번역한 주석, 의미 없는 주석 수 채우기를 금지한다.
shebang과 도구의 machine directive는 설명성 주석이 아니다.

check-comments는 현재 Python 주석·docstring과 Bash 전체 줄 주석을 검사한다.
Bash inline comment나 다른 언어를 도입하면 lexer와 검증 범위를 함께 확장한다.
핵심 로직의 이유가 충분한지, 누락이 있는지는 AGY / 사용자 검토로 확인한다.
