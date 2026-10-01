# Claude Code Bootstrap

이 파일은 Claude 전용 Harness가 아니라 기존 Repository-native Harness의 진입점이다.
작업 전에 다음 순서로 읽고 범위와 규칙을 그대로 적용한다.

1. [AGENTS.md](AGENTS.md)
2. [현재 Task](harness/workspace/current-task.md)
3. [기계 Registry](harness/registry.json)
4. Registry와 AGENTS가 연결한 Rules / Skills / Docs / Contracts

Claude는 Registry의 개발 Producer `claude`로 동작하며 Codex와 같은 current-task와 working tree를 이어서 작업할 수 있다.
Agent handoff는 Registry나 current-task의 Producer 설정을 바꾸지 않고 최신 checkpoint와 공동 개발 Evidence에서 재개한다.

- Task Report: `harness/workspace/reports/development/`
- Task Artifact: `harness/workspace/artifacts/development/<task-id>/`

Report에는 contributors와 finalized_by를 기록할 수 있지만 이는 Review 권한을 뜻하지 않는다.
AGY는 독립 Reviewer이며 Claude는 Review 원문·판정·승인 상태를 대신 작성하지 않는다.
검증 명령과 완료 절차는 AGENTS.md 및 현재 Task를 따른다.

## 실행 환경별 역할

- 로컬 Claude CLI: 위 개발 Producer `claude`다. 사용자 프롬프트를 받아 개발만 담당한다.
- 클라우드 세션(`CLAUDE_CODE_REMOTE=true`): 개발 Producer가 아니다. GitHub 읽기와 사용자와의 대화만 담당하며 [클라우드 세션 역할](harness/agents/claude-cloud-advisor.md)을 따른다. SessionStart hook이 이 역할을 자동으로 주입한다.
