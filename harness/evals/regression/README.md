# Harness Regression

정책 검사 오류·실패 누락이 발견되면 해당 입력과 기대 실패를 테스트로 보존한다.
기본 suite는 tests/contract/test_phase0.py와 tests/integration/test_phase0_cli.py다.
계약 오류·원문 변경·덮어쓰기·CLI 실패를 검사하며 제품 AI 성능을 평가하지 않는다.
Harness 변경 시 check-all 결과와 AGY 발견 사항을 changelog / report로 연결한다.
