#!/usr/bin/env python3
import ast
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tokenize
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import phase0


DYNAMIC_WORKSPACE_PATHS = [
    "harness/workspace/reports/*.md",
    "harness/workspace/checkpoints/*.md",
]


# 사용자가 독립 AGY 결과로 확인한 원문만 신뢰 기준에 고정해 Codex 보고서로 자기 승인하지 못하게 한다.
# 새 증거 추가는 별도 사용자 승인 Task이며 Registry의 경로나 checksum만 바꿔서는 승인되지 않는다.
ACCEPTED_AGY_REVIEWS = {
    "harness/workspace/reports/agy-initial-harness-review.md": {
        "sha256": "4567ebcec86fd820696f19928d251bd1b4b8b7c19118f7a033106f539f85b5dd",
        "reviewed_report": "harness/workspace/reports/2026-09-27-codex-harness-report.md",
        "reviewed_report_sha256": "c7c8b1c1da01746305cabe5b5f4790a870605b3f258d65792555443d78059d8c",
        "result": "pass_with_fixes",
    },
    "harness/workspace/reports/agy-harness-fix-review.md": {
        "sha256": "7516021d9945f67d662a5e4fe6e68fe51f1e1ebdb4510ec84f73bcb70985c1d4",
        "reviewed_report": "harness/workspace/reports/2026-09-27-codex-harness-fix-report.md",
        "reviewed_report_sha256": "1d5e68a85b599d59156d0e9038c73c4cbcf18d453ee282ebf46de96e2f852ada",
        "result": "pass",
    },
}


def run(*command, capture=False):
    result = subprocess.run(
        command, cwd=ROOT, text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
    )
    if result.returncode:
        raise ValueError(f"command failed ({result.returncode}): {' '.join(command)}\n{result.stderr or ''}")
    return result.stdout if capture else ""


def project_files():
    output = run("git", "ls-files", "--cached", "--others", "--exclude-standard", "-z", capture=True)
    return sorted(set(item for item in output.split("\0") if item))


def registry():
    return phase0.read_json(ROOT / "harness/registry.json")


def dynamic_workspace(spec):
    # 경로 예외를 넓혀 정적 규칙이나 실행 코드를 우회 등록하지 못하도록 승인된 두 경계만 인정한다.
    if spec["dynamic_paths"] != DYNAMIC_WORKSPACE_PATHS:
        raise ValueError("dynamic Workspace path policy drift")
    tracked = set(run("git", "ls-files", "-z", capture=True).split("\0")) - {""}
    listed = set(project_files())
    workspace = set()
    for pattern in spec["dynamic_paths"]:
        directory = ROOT / Path(pattern).parent
        if directory.is_symlink() or directory.resolve() != directory or not directory.is_dir():
            raise ValueError(f"unsafe dynamic Workspace directory: {directory.relative_to(ROOT)}")
        # Git이 제외한 파일도 직접 검사해야 ignore나 symlink로 외부 기억을 숨길 수 없다.
        names = {str(path.relative_to(ROOT)) for path in directory.iterdir()}
        names.update(name for name in listed if (ROOT / name).is_relative_to(directory))
        for name in sorted(names):
            path = ROOT / name
            if (path.parent != directory or path.suffix != ".md" or path.is_symlink()
                    or path.resolve() != path or not path.is_file() or os.access(path, os.X_OK)):
                raise ValueError(f"unsafe dynamic Workspace file: direct non-executable Markdown regular file required: {name}")
            if name in spec["required_files"] and path.name != "README.md":
                raise ValueError(f"dynamic Workspace files must not be individually registered: {name}")
        if names:
            ignored = subprocess.run(
                ["git", "check-ignore", "--no-index", *sorted(names)],
                cwd=ROOT, text=True, capture_output=True,
            )
            if ignored.returncode not in (0, 1):
                raise ValueError("git check-ignore failed")
            if ignored.stdout:
                raise ValueError("dynamic Workspace files are ignored:\n" + ignored.stdout)
        for name in sorted(names):
            if name not in tracked:
                raise ValueError(f"untracked dynamic Workspace file: {name}")
        workspace.update(names)
    return workspace


def compose():
    result = json.loads(run("docker", "compose", "-f", "docker-compose.yml", "config", "--format", "json", capture=True))
    if set(result["services"]) != set(registry()["compose_services"]):
        raise ValueError("Compose services differ from implementation registry")
    service = result["services"]["phase0"]
    if service["entrypoint"] != ["python3", "-B", "/workspace/scripts/phase0.py"]:
        raise ValueError("Compose does not execute the current Phase 0 tool")
    # 지금은 로컬 증거 보존 Batch이므로 외부 호출과 컨테이너 내부 쓰기를 막아 수집 기능으로 확장되지 않게 한다.
    if service.get("network_mode") != "none" or service.get("read_only") is not True:
        raise ValueError("Phase 0 local Batch boundary drift")
    # 도구 실행이 코드나 Review 증거를 바꾸지 못하도록 저장소는 읽기 전용이고 데이터·재생성 결과만 쓴다.
    expected = {"/workspace": (ROOT, True), "/data": (ROOT / "data", False),
                "/artifacts": (ROOT / "harness/workspace/artifacts", False)}
    mounts = {item["target"]: item for item in service["volumes"]}
    if set(mounts) != set(expected):
        raise ValueError("Compose mounts drift")
    for target, (source, readonly) in expected.items():
        mount = mounts[target]
        if Path(mount["source"]).resolve() != source.resolve() or bool(mount.get("read_only")) != readonly:
            raise ValueError(f"Compose mount drift: {target}")


def setup_check():
    if sys.version_info < (3, 11):
        raise ValueError("Python >=3.11 required")
    run("bash", "--version", capture=True)
    run("git", "--version", capture=True)
    version = run("docker", "compose", "version", "--short", capture=True).strip()
    match = re.match(r"v?(\d+)\.", version)
    if not match or int(match[1]) < 2:
        raise ValueError("Docker Compose >=2 required")
    compose()
    print(f"PASS: Python {sys.version.split()[0]}, Bash, Git, Compose {version}; configuration only")
    print("N/A: no Java/Node/MySQL/Qdrant/services/credentials; daemon checked only when running Batch")


def format_check():
    for name in project_files():
        path = ROOT / name
        if not path.is_file():
            raise ValueError(f"missing project file: {name}")
        raw = path.read_bytes()
        text = raw.decode("utf-8")
        if not raw or not raw.endswith(b"\n") or b"\r" in raw:
            raise ValueError(f"UTF-8/LF/final newline required: {name}")
        if any(line.rstrip(" \t") != line for line in text.splitlines()):
            raise ValueError(f"trailing whitespace: {name}")
        if name.endswith(".json"):
            expected = json.dumps(phase0.read_json(path), ensure_ascii=False, indent=2, allow_nan=False) + "\n"
            if text != expected:
                raise ValueError(f"JSON requires 2-space canonical indentation: {name}")
    run("git", "diff", "--check")
    run("git", "diff", "--cached", "--check")
    print("PASS: repository text/JSON format and Git whitespace")


def lint_check():
    for name in project_files():
        path = ROOT / name
        if name.endswith(".py"):
            ast.parse(path.read_text(encoding="utf-8"), filename=name)
        elif name.endswith(".sh"):
            run("bash", "-n", name)
            if not os.access(path, os.X_OK):
                raise ValueError(f"shell entry point is not executable: {name}")
        elif name.endswith(".json"):
            phase0.read_json(path)
    print("PASS: Python AST, Bash syntax/executable modes, strict JSON keys")


def contract_check():
    run(sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests/contract", "-p", "test_*.py", "-v")
    print("PASS: snapshot/report, upstream Probe, API-quality and bounded document mock-transport Unit and Contract tests")
    print("N/A in offline validation: live HTTP, full provider specification, product API and Qdrant contracts")


def integration_check():
    run(sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests/integration", "-p", "test_*.py", "-v")
    print("PASS: local CLI integration including credential-missing Probe/API-quality and bounded document failure exits; no live HTTP")
    print("N/A: live API/document HTTP, document text Parser, service/DB integration")


def allowed_ignored(name):
    path = Path(name)
    parts = path.parts
    if path.name == ".DS_Store" or path.name.endswith(".pyc"):
        return True
    if any(part in {".venv", "__pycache__", ".pytest_cache"} for part in parts):
        return True
    # IDE가 생성한 로컬 설정은 제외하되 같은 경로의 코드·보고서까지 숨기는 예외로 확장하지 않는다.
    if len(parts) >= 2 and parts[0] == ".idea":
        return path.suffix in {".xml", ".iml"} or path.name == ".gitignore"
    # 실제 credential은 제외하지만 변수 계약을 보여주는 example은 사용자가 Diff로 검토해야 한다.
    if len(parts) == 1 and (name == ".env" or name.startswith(".env.")) and name != ".env.example":
        return True
    if len(parts) >= 3 and parts[0] == "data" and parts[1] in {"raw", "downloaded", "parsed", "failed"}:
        # 원문 payload와 작업 산출물을 구분해 데이터 디렉터리에서도 규칙·코드·보고서는 숨기지 않는다.
        return path.suffix.lower() not in {".md", ".py", ".sh", ".yml", ".yaml"} and path.name != "README.md"
    # 재생성 가능한 실행 로그만 제외하며 사람이 판단할 해석과 결론은 추적된 Markdown Report에 남긴다.
    return len(parts) == 4 and parts[:3] == ("harness", "workspace", "artifacts") and path.suffix in {".json", ".log"}


def git_check():
    branch = run("git", "branch", "--show-current", capture=True).strip()
    # CI checkout의 detached HEAD는 dev Push ref로만 인정해 로컬 브랜치 제한을 우회하지 않는다.
    ci_dev = (os.environ.get("GITHUB_ACTIONS") == "true"
              and os.environ.get("GITHUB_EVENT_NAME") == "push"
              and os.environ.get("GITHUB_REF") == "refs/heads/dev")
    if branch != "dev" and not (not branch and ci_dev):
        raise ValueError(f"development must be on dev: {branch or 'detached HEAD'}")
    # CI에 Secret 파일이 없어도 ignore 정책 누락을 잡아 향후 사용자 키가 추적되는 것을 막는다.
    ignored_profiles = run("git", "check-ignore", "--no-index", ".env.dev", ".env.prod", capture=True).splitlines()
    if set(ignored_profiles) != {".env.dev", ".env.prod"}:
        raise ValueError("profile secret files must be ignored: .env.dev / .env.prod")
    untracked = run("git", "ls-files", "--others", "--exclude-standard", "-z", capture=True)
    if untracked:
        raise ValueError("untracked project files:\n" + untracked.replace("\0", "\n"))
    if run("git", "diff", "--name-only", "--diff-filter=U", capture=True).strip():
        raise ValueError("unresolved Git conflicts")
    indexed_new = set(run("git", "diff", "--cached", "--name-only", "--diff-filter=A", "-z", capture=True).split("\0"))
    unstaged = set(run("git", "diff", "--name-only", "-z", capture=True).split("\0"))
    if (indexed_new & unstaged) - {""}:
        raise ValueError("new indexed files differ from working files; update their explicit Git entries")
    required = registry()["required_files"]
    # global ignore까지 검사해 설계·검증·보고서가 Git 밖에 숨겨지는 것을 막는다.
    ignored_required = subprocess.run(
        ["git", "check-ignore", "--no-index", *required],
        cwd=ROOT, text=True, capture_output=True,
    )
    if ignored_required.returncode not in (0, 1):
        raise ValueError("git check-ignore failed")
    if ignored_required.stdout:
        raise ValueError("required files are ignored:\n" + ignored_required.stdout)
    ignored = run("git", "ls-files", "--others", "--ignored", "--exclude-standard", "-z", capture=True)
    for name in ignored.split("\0"):
        if name and not allowed_ignored(name):
            raise ValueError(f"ignored project result: {name}")
    tracked = run("git", "ls-files", "-z", capture=True)
    for name in tracked.split("\0"):
        if name and allowed_ignored(name):
            raise ValueError(f"raw/secret/cache must not be tracked: {name}")
    dynamic_workspace(registry())
    print("PASS: dev policy, tracked changes, ignore boundary, index visibility")
    run("git", "status", "--short", "--branch")


def has_korean(text):
    return bool(re.search(r"[가-힣]", text))


def comments_check():
    checked = 0
    for name in project_files():
        path = ROOT / name
        if name.endswith(".py"):
            source = path.read_text(encoding="utf-8")
            for item in tokenize.generate_tokens(io.StringIO(source).readline):
                if item.type == tokenize.COMMENT and not item.string.startswith("#!"):
                    checked += 1
                    if not has_korean(item.string):
                        raise ValueError(f"explanatory comment requires Korean: {name}:{item.start[0]}")
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    text = ast.get_docstring(node)
                    if text and not has_korean(text):
                        raise ValueError(f"docstring requires Korean: {name}")
        elif name.endswith(".sh"):
            for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if line.lstrip().startswith("#") and not line.startswith("#!"):
                    checked += 1
                    if not has_korean(line):
                        raise ValueError(f"explanatory comment requires Korean: {name}:{index}")
    print(f"PASS: Korean explanatory comments ({checked} checked); WHY/omissions need AGY review")


def markdown_links(path):
    source = path.read_text(encoding="utf-8")
    # 코드 예제 안의 문자열은 문서 navigation 링크가 아니므로 fence를 제외한다.
    source = re.sub(r"(?ms)^\s*```.*?^\s*```[^\n]*$", "", source)
    for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", source):
        target = unquote(target.strip("<>").split("#", 1)[0])
        if not target or re.match(r"[A-Za-z][A-Za-z0-9+.-]*:", target):
            continue
        destination = (path.parent / target).resolve()
        if not destination.is_relative_to(ROOT) or not destination.exists():
            raise ValueError(f"broken/outside documentation link: {path.relative_to(ROOT)} -> {target}")


def review_status(spec, workspace):
    state = spec["agy_review"]
    evidence = spec["agy_review_evidence"]
    if state not in ("pending", "review_complete"):
        raise ValueError("AGY review: unsupported lifecycle state")
    if state == "pending":
        if evidence is not None:
            raise ValueError("AGY review: pending requires null evidence")
        return "PENDING: independent AGY review of current report; human review"
    if not isinstance(evidence, str) or evidence not in ACCEPTED_AGY_REVIEWS:
        raise ValueError("AGY review: independent evidence must be user-acknowledged")
    accepted = ACCEPTED_AGY_REVIEWS[evidence]
    for name, expected_hash in (
        (evidence, accepted["sha256"]),
        (accepted["reviewed_report"], accepted["reviewed_report_sha256"]),
    ):
        path = ROOT / name
        # Reviewer 이름이나 COMPLETE 문구만으로는 저자를 증명할 수 없어 독립 원문과 검토 대상의 byte를 대조한다.
        if name not in workspace or path.is_symlink() or path.resolve() != path or not path.is_file():
            raise ValueError(f"AGY review: missing or unsafe evidence/basis: {name}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash:
            raise ValueError(f"AGY review: evidence/basis checksum mismatch: {name}")
    summary = f"AGY: review_complete; result={accepted['result']}; reviewed_report={accepted['reviewed_report']}"
    # 이전 Review를 이후 수정의 승인으로 오해하지 않도록 현재 보고서와 검토 대상의 범위를 구분한다.
    current = "complete" if spec["report"] == accepted["reviewed_report"] else "pending"
    return summary + f"\nCURRENT REPORT REVIEW: {current}; human review PENDING"


def harness_check():
    spec = registry()
    actual = set(project_files())
    expected = set(spec["required_files"])
    workspace = dynamic_workspace(spec)
    # 기록은 경로·안전 규칙으로 검증하고 고정 README를 포함한 정적 구조는 개별 Registry와 대조한다.
    static_actual = actual - (workspace - expected)
    if static_actual != expected:
        raise ValueError(f"Registry drift: missing={sorted(expected - static_actual)}, unregistered={sorted(static_actual - expected)}")
    if spec["phase"] != "phase0-preparation":
        raise ValueError("phase must reflect actual preparation")
    # 현재 Task가 과거 Report를 승인받은 것처럼 보이지 않도록 활성 Report 연결도 함께 검증한다.
    task = (ROOT / "harness/workspace/current-task.md").read_text(encoding="utf-8")
    final_reports = re.findall(r"\[Final Report\]\(([^)]+)\)", task)
    if len(final_reports) != 1 or (
        ROOT / "harness/workspace" / final_reports[0]
    ).resolve() != (ROOT / spec["report"]).resolve():
        raise ValueError("current-task Final Report differs from Registry report")
    status = review_status(spec, workspace)
    if spec["branches"] != {"development": "dev", "verified": "main", "deployment": "op"}:
        raise ValueError("branch policy drift")
    for name in actual:
        path = ROOT / name
        if not path.is_file():
            raise ValueError(f"missing registered file: {name}")
        if name.endswith(".md"):
            markdown_links(path)
    skill_paths = {str(path.relative_to(ROOT)) for path in (ROOT / "harness/skills").glob("*/SKILL.md")}
    if skill_paths != set(spec["skills"]):
        raise ValueError("Skill Registry drift")
    for category in ("rules", "agents"):
        paths = {str(path.relative_to(ROOT)) for path in (ROOT / "harness" / category).glob("*.md")}
        if paths != set(spec[category]):
            raise ValueError(f"{category} Registry drift")
    entry = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    # 진입점이 상세 설명서로 커지면 매 Task마다 불필요한 Context를 읽게 되어 routing 역할을 잃는다.
    if len(entry.splitlines()) > 100:
        raise ValueError("AGENTS.md must stay a concise registry")
    for name in spec["skills"]:
        if name not in entry:
            raise ValueError(f"Skill missing from AGENTS routing: {name}")
        text = (ROOT / name).read_text(encoding="utf-8")
        match = re.match(r"---\nname: ([a-z0-9-]+)\ndescription: ([^\n]+)\n---\n", text)
        if not match or match[1] != Path(name).parent.name or not match[2].strip():
            raise ValueError(f"invalid Skill frontmatter: {name}")
        if "[TODO:" in text:
            raise ValueError(f"unfinished Skill scaffold: {name}")
    actual_code = {name for name in actual if Path(name).suffix in {".py", ".sh"}}
    if actual_code != set(spec["execution_files"]):
        raise ValueError("new executable code requires registered validation")
    for name in spec["validation_commands"]:
        if name not in actual_code or not os.access(ROOT / name, os.X_OK):
            raise ValueError(f"missing validation command: {name}")
    if any((ROOT / name).exists() for name in spec["unimplemented_modules"]):
        raise ValueError("product module added outside current phase; update scope and validation first")
    workflows = {str(path.relative_to(ROOT)) for path in (ROOT / ".github/workflows").glob("*") if path.is_file()}
    if workflows != {".github/workflows/ci.yml"}:
        raise ValueError("workflow/deployment drift")
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    if not re.search(r"^on:\n  push:\n    branches: \[dev\]\npermissions:\n  contents: read\n", ci, re.MULTILINE):
        raise ValueError("CI must enforce dev Push and read-only contents")
    for command in ("./scripts/setup.sh", "./scripts/check-all.sh"):
        if f"run: {command}" not in ci:
            raise ValueError(f"CI missing required command: {command}")
    compose()
    report = ROOT / spec["report"]
    if spec["report"] not in workspace or not report.is_file() or not report.read_text(encoding="utf-8").strip():
        raise ValueError("task Report missing")
    print("PASS: docs/links, Skills/Rules Registry, commands, phase, Compose/CI and external memory")
    print(status)


CHECKS = {
    "setup": setup_check, "format": format_check, "lint": lint_check,
    "contract": contract_check, "integration": integration_check,
    "git-tracked": git_check, "comments": comments_check, "harness": harness_check,
}


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in CHECKS:
        print("usage: validate.py " + "|".join(CHECKS), file=sys.stderr)
        return 2
    try:
        CHECKS[sys.argv[1]]()
    except (ValueError, OSError, TypeError, KeyError, SyntaxError, tokenize.TokenError) as error:
        print(f"FAIL [{sys.argv[1]}]: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
