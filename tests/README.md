# 현재 테스트

contract/test_phase0.py: 로컬 도구 Unit / Contract, 잘못된 측정·metadata·경로·hash 거부.
integration/test_phase0_cli.py: 임시 디렉터리에서 실제 CLI 전체 흐름과 실패 종료 확인.
contract/test_harness_policy.py: 격리된 Git 저장소에서 링크·CI·브랜치·ignore·주석·범위 오류와
check-all 실패 전파를 검증한다.
AGY Lifecycle·독립 원문/검토 대상 변조·자기 승인·Review 범위·IDE 문서 숨김의 거부도 검사한다.
실 API·네트워크·DB·Parser·제품 E2E는 실행하지 않는다.
Fixture는 합성 metadata / report이며 실제 데이터 성공률의 근거가 아니다.
