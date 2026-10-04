#!/usr/bin/env python3
import ast
import hashlib
import importlib.util
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
# 제품 검증은 고정 requirements 환경에서 실행한다. 셸을 activate하지 않아도 기존 검증 진입점을 유지한다.
venv_python = ROOT / ".venv/bin/python"
if venv_python.exists() and Path(sys.prefix) != ROOT / ".venv":
    os.execv(str(venv_python), [str(venv_python), "-B", *sys.argv])
if venv_python.exists():
    os.environ["PATH"] = str(venv_python.parent) + os.pathsep + os.environ.get("PATH", "")
sys.path.insert(0, str(ROOT / "scripts"))
import phase0


# Phase를 추가할 때 목록 하나만 갱신해야 setup·integration·harness 사이의 DB 준비 누락이 생기지 않는다.
DATABASE_PHASES = ("phase1a-structured-pilot", "phase1b-full-sync", "phase2-document-acquisition",
                   "phase2-5-s3-storage", "phase3-document-parsing", "phase4-document-indexing",
                   "phase5-document-retrieval", "phase6-rag-answer")
SERVICE_BUILD_OUTPUTS = {("backend", "build"), ("backend", ".gradle"), ("frontend", "node_modules"), ("frontend", "dist")}
DYNAMIC_WORKSPACE_PATHS = [
    "harness/workspace/reports/**/*.md",
    "harness/workspace/checkpoints/**/*.md",
    "harness/workspace/artifacts/**/*.json",
    "harness/workspace/artifacts/**/*.log",
]
STATIC_WORKSPACE_FILES = {
    "STATIC_CONTROL": ["harness/workspace/current-task.md",
                       "harness/workspace/artifacts/development/regression-set/run.py"],
    "STATIC_DOCUMENTATION": [
        "harness/workspace/artifacts/README.md",
        "harness/workspace/checkpoints/README.md",
    ],
}
TASK_OUTPUT_PATHS = {
    "development": {
        "reports": "harness/workspace/reports/development/",
        "artifacts": "harness/workspace/artifacts/development/<task-id>/",
    },
    "agy": {
        "reports": "harness/workspace/reports/agy/",
        "artifacts": "harness/workspace/artifacts/agy/<review-id>/",
    },
}
DEVELOPMENT_PRODUCERS = ("codex", "claude")
INDEPENDENT_REVIEWER = "agy"
PRODUCER_INSTRUCTION_FILES = {
    "codex": "harness/agents/codex-developer.md",
    "claude": "CLAUDE.md",
    "agy": "harness/agents/agy-reviewer.md",
}


# 사용자가 독립 AGY 결과로 확인한 원문만 신뢰 기준에 고정해 개발 보고서로 자기 승인하지 못하게 한다.
# 새 증거 추가는 별도 사용자 승인 Task이며 Registry의 경로나 checksum만 바꿔서는 승인되지 않는다.
ACCEPTED_AGY_REVIEWS = {
    "harness/workspace/reports/agy/agy-initial-harness-review.md": {
        "sha256": "4567ebcec86fd820696f19928d251bd1b4b8b7c19118f7a033106f539f85b5dd",
        "reviewed_report": "harness/workspace/reports/codex/2026-09-27-codex-harness-report.md",
        "reviewed_report_sha256": "c7c8b1c1da01746305cabe5b5f4790a870605b3f258d65792555443d78059d8c",
        "result": "pass_with_fixes",
    },
    "harness/workspace/reports/agy/agy-harness-fix-review.md": {
        "sha256": "7516021d9945f67d662a5e4fe6e68fe51f1e1ebdb4510ec84f73bcb70985c1d4",
        "reviewed_report": "harness/workspace/reports/codex/2026-09-27-codex-harness-fix-report.md",
        "reviewed_report_sha256": "1d5e68a85b599d59156d0e9038c73c4cbcf18d453ee282ebf46de96e2f852ada",
        "result": "pass",
    },
}


def run(*command, capture=False):
    result = subprocess.run(
        command, cwd=ROOT, text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        # BOUNDARY: test runtime은 모델을 네트워크에서 받지 않고 준비된 artifacts만 사용한다.
        # 터미널에서 실행하면 git diff가 pager(less)를 열어 (END)에서 멈추므로 검증용 git 호출은 pager 없이 출력한다.
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", HF_HUB_OFFLINE="1", GIT_PAGER="cat"),
    )
    if result.returncode:
        raise ValueError(f"command failed ({result.returncode}): {' '.join(command)}\n{result.stderr or ''}")
    return result.stdout if capture else ""


def workspace_category(name):
    # BOUNDARY: 사용자가 지정한 Task handoff는 실행 상태 산출물이며 current-task와 다르다.
    if name in ("harness/workspace/handoff/bundle1-handoff.md", "harness/workspace/handoff/bundle2-handoff.md",
                "harness/workspace/handoff/bundle3-handoff.md", "harness/workspace/handoff/bundle4-handoff.md",
                "harness/workspace/handoff/bundle5-1-handoff.md"):
        return "GENERATED_CHECKPOINT"
    for category, names in STATIC_WORKSPACE_FILES.items():
        if name in names:
            return category
    path = Path(name)
    parts = path.parts
    if path.is_absolute() or ".." in parts:
        return None
    if len(parts) < 3 or parts[:2] != ("harness", "workspace"):
        return None
    if path.name == ".DS_Store":
        return "GENERATED_ARTIFACT"
    if len(parts) >= 4:
        if parts[2] == "reports" and path.suffix == ".md":
            return "GENERATED_REPORT"
        if parts[2] == "checkpoints" and path.suffix == ".md":
            return "GENERATED_CHECKPOINT"
        if parts[2] == "artifacts" and path.suffix in {".json", ".log"}:
            return "GENERATED_ARTIFACT"
    return None


def generated_output(name):
    # 경로 이름만으로 코드를 숨기지 않도록 실제 산출물 종류와 고정 제어 문서를 분리한다.
    return (workspace_category(name) or "").startswith("GENERATED_")


def project_files():
    output = run("git", "ls-files", "--cached", "--others", "--exclude-standard", "-z", capture=True)
    return sorted(set(item for item in output.split("\0") if item and not generated_output(item)))


def registry():
    return phase0.read_json(ROOT / "harness/registry.json")


def workspace_policy(spec):
    # 출력 예외가 제품·규칙·current-task까지 확장되면 검증 입력을 숨기므로 승인된 분류만 허용한다.
    if spec["dynamic_paths"] != DYNAMIC_WORKSPACE_PATHS or spec["workspace_static_files"] != STATIC_WORKSPACE_FILES:
        raise ValueError("dynamic Workspace path policy drift")
    # Task 역할 경로는 정적 제어 정책으로 검증한다. 산출물 파일의 존재나 형식으로 build를 승인하지 않는다.
    if spec.get("task_output_paths") != TASK_OUTPUT_PATHS:
        raise ValueError("task output path policy drift")
    if spec.get("development_producers") != list(DEVELOPMENT_PRODUCERS):
        raise ValueError("development producer identity drift")
    if spec.get("independent_reviewer") != INDEPENDENT_REVIEWER:
        raise ValueError("independent reviewer identity drift")
    if "active_producer" in spec:
        raise ValueError("active producer must not gate same-task handoff")
    for producer in DEVELOPMENT_PRODUCERS:
        instructions = (ROOT / PRODUCER_INSTRUCTION_FILES[producer]).read_text(encoding="utf-8")
        if any(f"`{path}`" not in instructions for path in TASK_OUTPUT_PATHS["development"].values()):
            raise ValueError(f"development output instructions drift: {producer}")
    reviewer_instructions = (ROOT / PRODUCER_INSTRUCTION_FILES[INDEPENDENT_REVIEWER]).read_text(encoding="utf-8")
    if any(f"`{path}`" not in reviewer_instructions for path in TASK_OUTPUT_PATHS["agy"].values()):
        raise ValueError("reviewer output instructions drift")
    if not set(sum(STATIC_WORKSPACE_FILES.values(), [])).issubset(spec["required_files"]):
        raise ValueError("static Workspace anchors must remain registered")
    for name in spec["required_files"]:
        if generated_output(name):
            raise ValueError(f"dynamic Workspace files must not be individually registered: {name}")


def compose():
    sys.path.insert(0, str(ROOT / "data-pipeline/src"))
    from biz_aid_pipeline.config.settings import profile_values
    config = profile_values(ROOT, "dev", {"MYSQL_PORT", "MYSQL_DATABASE", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_ROOT_PASSWORD"})
    # 설정 검증도 generic .env를 읽지 않는다. CI는 Profile 파일 없이 Process Environment로 검증할 수 있다.
    env_file = str(ROOT / ".env.dev") if (ROOT / ".env.dev").is_file() else os.devnull
    configured = subprocess.run(["docker", "compose", "--env-file", env_file, "--profile", "*", "-f", "docker-compose.yml", "config", "--format", "json"],
        cwd=ROOT, text=True, capture_output=True, env=dict(os.environ, **config, COMPOSE_DISABLE_ENV_FILE="1"))
    # Compose 설정 오류가 사용자 env의 값을 반사할 수 있으므로 stderr와 설정 JSON을 출력하지 않는다.
    if configured.returncode:
        raise ValueError("Compose configuration failed; output withheld to protect credentials")
    result = json.loads(configured.stdout)
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
    if registry()["phase"] in DATABASE_PHASES:
        mysql = result["services"]["mysql"]
        flyway = result["services"]["flyway"]
        ports = mysql.get("ports", [])
        if (mysql["profiles"] != ["dev-db", "app"] or len(ports) != 1
                or ports[0].get("host_ip") != "127.0.0.1" or str(ports[0]["published"]) != "3306"
                or ports[0]["target"] != 3306 or mysql["environment"]["MYSQL_DATABASE"] != "biz_aid_dev"):
            raise ValueError("dev MySQL local boundary drift")
        migration = flyway["volumes"]
        if (flyway["profiles"] != ["dev-db"] or len(migration) != 1 or not migration[0].get("read_only")
                or Path(migration[0]["source"]).resolve() != ROOT / "migrations"
                or flyway["environment"].get("FLYWAY_CLEAN_DISABLED") != "true"
                or flyway["environment"].get("FLYWAY_URL") != "jdbc:mysql://mysql:3306/biz_aid_dev?allowPublicKeyRetrieval=true&useSSL=false"):
            raise ValueError("common Flyway ownership boundary drift")
        qdrant = result["services"]["qdrant"]
        ports = qdrant.get("ports", [])
        # BOUNDARY: 개발 vector index는 dev profile에서 loopback으로만 열고 인증 없는 Qdrant를 외부에 노출하지 않는다.
        if (qdrant["profiles"] != ["dev-vector", "app"] or len(ports) != 1 or ports[0].get("host_ip") != "127.0.0.1"
                or str(ports[0]["published"]) != "6333" or ports[0]["target"] != 6333):
            raise ValueError("dev Qdrant local boundary drift")
        # BOUNDARY: 서비스 V1(app profile)은 같은 dev MySQL을 쓰고 loopback으로만 연다. React 컨테이너는 Spring만 proxy한다.
        for name, target in (("backend", 8080), ("frontend", 80), ("fastapi", 8000)):
            service = result["services"].get(name, {})
            ports = service.get("ports", [])
            if (service.get("profiles") != ["app"] or len(ports) != 1 or ports[0].get("host_ip") != "127.0.0.1"
                    or ports[0]["target"] != target):
                raise ValueError(f"service V1 {name} local boundary drift")
        backend = result["services"]["backend"]
        mounts = {item["target"]: item for item in backend.get("volumes", [])}
        # BOUNDARY: Spring은 공통 migration과 공통 계약(기업 지역 표준명)만 읽기 전용으로 붙인다.
        if (backend["environment"].get("MYSQL_HOST") != "mysql" or set(mounts) != {"/migrations", "/contracts"}
                or not all(item.get("read_only") for item in mounts.values())
                or Path(mounts["/migrations"]["source"]).resolve() != ROOT / "migrations"
                or Path(mounts["/contracts"]["source"]).resolve() != ROOT / "contracts"
                or backend["environment"].get("BIZAID_CONTRACTS_PATH") != "/contracts"
                or backend["environment"].get("FLYWAY_LOCATIONS") != "filesystem:/migrations"):
            raise ValueError("service V1 backend must use common Flyway migrations and the compose MySQL")
        # BOUNDARY(IMP-017): FastAPI 컨테이너는 질문 처리 전용이다. 코드·계약·모델을 읽기 전용으로만 붙이고, 데이터는 compose의
        # MySQL·Qdrant만 쓰며, Ollama는 host를 부른다. Spring은 compose 안에서 이 컨테이너를 부른다.
        fastapi = result["services"]["fastapi"]
        environment = fastapi.get("environment", {})
        mounts = {item["target"]: item for item in fastapi.get("volumes", [])}
        if (set(mounts) != {"/app/data-pipeline/src", "/app/contracts", "/models", "/home/bizaid/.aws"} or not all(item.get("read_only") for item in mounts.values())
                or Path(mounts["/app/data-pipeline/src"]["source"]).resolve() != ROOT / "data-pipeline/src"
                or Path(mounts["/app/contracts"]["source"]).resolve() != ROOT / "contracts"
                or Path(mounts["/home/bizaid/.aws"]["source"]).resolve() != Path.home() / ".aws"
                or environment.get("MYSQL_HOST") != "mysql" or environment.get("QDRANT_URL") != "http://qdrant:6333"
                or environment.get("OLLAMA_BASE_URL") != "http://host.docker.internal:11434"
                or environment.get("BIZAID_DOCLING_ARTIFACTS_PATH") != "/models"
                or backend["environment"].get("AI_BASE_URL") != "http://fastapi:8000"):
            raise ValueError("FastAPI container boundary drift")
        # nginx가 시작 시점의 backend IP를 계속 쓰지 않도록 backend가 바뀌면 frontend도 다시 시작한다.
        frontend_backend = result["services"]["frontend"].get("depends_on", {}).get("backend", {})
        if frontend_backend.get("restart") is not True:
            raise ValueError("frontend must restart with backend (stale nginx upstream IP)")


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
    if registry()["phase"] in DATABASE_PHASES:
        import pydantic
        import sqlalchemy
        import pymysql
        if not pydantic.__version__.startswith("2.") or not sqlalchemy.__version__.startswith("2."):
            raise ValueError("Phase 1A requires Pydantic v2 and SQLAlchemy v2")
        print("PASS: Pydantic v2, SQLAlchemy v2, PyMySQL available; DB tested in integration")
    # Phase 4 chunking·indexing도 같은 고정 artifact와 parser 결과를 소비하므로 parsing 전제 검사를 유지한다.
    if registry()["phase"] in ("phase3-document-parsing", "phase4-document-indexing", "phase5-document-retrieval", "phase6-rag-answer"):
        import docling_core
        try:
            import lzma
        except ImportError:
            raise ValueError("Docling PDF prerequisite missing: Python 3.11 with stdlib lzma (_lzma) is required") from None
        os.environ["HF_HUB_OFFLINE"] = "1"
        from docling.document_converter import DocumentConverter
        sys.path.insert(0, str(ROOT / "data-pipeline/src"))
        from biz_aid_pipeline.parsing.models import docling_artifacts_path, model_artifacts_sha256, parsing_contract
        try:
            artifacts = docling_artifacts_path(parsing_contract())
            model_artifacts_sha256(parsing_contract())
        except ValueError as error:
            raise ValueError(f"Docling model artifacts not provisioned ({error}); see data-pipeline/README.md") from None
        # BOUNDARY: 3-B는 OCR 없는 native PDF baseline이므로 OCR engine이 설치돼 있으면 설정 실수로 켜질 여지를 막는다.
        present = [name for name in ("rapidocr", "easyocr", "tesserocr", "ocrmac") if importlib.util.find_spec(name)]
        if present:
            raise ValueError(f"OCR engine must not be installed in Phase 3 PDF baseline: {present}")
        # BOUNDARY: PP 표 engine은 설치 여부만 확인하고 모델 적재·추론은 Contract test에서 한다. paddleocr 배포는 쓰지 않는다.
        if importlib.util.find_spec("paddlex") is None or importlib.util.find_spec("paddle") is None:
            raise ValueError("PP-TableMagic table engine (paddlepaddle, paddlex[ocr]) missing; install data-pipeline/requirements.txt")
        if importlib.util.find_spec("paddleocr"):
            raise ValueError("paddleocr must not be installed; the PDF table engine uses paddlex without OCR models")
        print(f"PASS: docling-core, Docling PDF converter, PP-TableMagic engine, lzma and pinned model artifacts ({artifacts.name}) "
              "identity verified; OCR engines absent; HF offline")
    if registry()["phase"] in ("phase4-document-indexing", "phase5-document-retrieval", "phase6-rag-answer"):
        if importlib.util.find_spec("qdrant_client") is None:
            raise ValueError("qdrant-client missing; install data-pipeline/requirements.txt")
        print("PASS: qdrant-client available; dev Qdrant server is tested outside check-all")
    print("N/A: Java/Node builds and live upstream, Qdrant server, LLM calls; separate service validation")


def format_check():
    files = project_files()
    for name in files:
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
    # 이미 추적된 생성물도 Git diff에 남으므로 입력 자산의 경로만 명시해 공백을 검사한다.
    run("git", "diff", "--check", "--", *files)
    run("git", "diff", "--cached", "--check", "--", *files)
    print("PASS: static/project text/JSON format and Git whitespace; generated outputs excluded")


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
    print("PASS: offline Contract tests from Phase 0 through parsing, indexing, retrieval, RAG, Eligibility, internal API and V1 baseline helpers")
    print("N/A in offline validation: live HTTP/AWS/Qdrant/LLM, real HWP conversion and Browser E2E")


def integration_check():
    if registry()["phase"] in DATABASE_PHASES:
        run(sys.executable, "-B", "infra/dev_mysql.py")
    run(sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests/integration", "-p", "test_*.py", "-v")
    print("PASS: local CLI and dev/test MySQL integration for structured ingestion, document metadata and parse persistence")
    print("N/A: live API/document HTTP, AWS, real HWP conversion, Backend/Frontend and Browser E2E")


def database_comment_problem(name, comment):
    value = (comment or "").strip()
    if not value:
        return "missing"
    normalized = re.sub(r"[^\w가-힣]", "", value.casefold()).replace("_", "")
    object_name = re.sub(r"[^\w가-힣]", "", name.casefold()).replace("_", "")
    if re.search(r"todo|tbd", value, re.IGNORECASE) or normalized in {"데이터", "값", object_name}:
        return "placeholder_or_name_only"
    if not has_korean(value):
        return "korean_description_required"
    return None


def database_comments(connection):
    from sqlalchemy import text
    schema = connection.execute(text("SELECT DATABASE()")).scalar_one()
    if schema not in ("biz_aid_dev", "biz_aid_test"):
        raise ValueError("database comment validation requires the application dev/test schema")
    # 새 업무 테이블을 이름 목록에서 빠뜨리지 않도록 DB 경계를 조회하고 Flyway 내부 테이블만 제외한다.
    tables = connection.execute(text("""
        SELECT TABLE_NAME, TABLE_COMMENT FROM information_schema.tables
        WHERE TABLE_SCHEMA = :schema AND TABLE_TYPE = 'BASE TABLE'
          AND TABLE_NAME <> 'flyway_schema_history' ORDER BY TABLE_NAME
    """), {"schema": schema}).mappings().all()
    columns = connection.execute(text("""
        SELECT c.TABLE_NAME, c.COLUMN_NAME, c.COLUMN_COMMENT
        FROM information_schema.columns c JOIN information_schema.tables t
          ON t.TABLE_SCHEMA = c.TABLE_SCHEMA AND t.TABLE_NAME = c.TABLE_NAME
        WHERE c.TABLE_SCHEMA = :schema AND t.TABLE_TYPE = 'BASE TABLE'
          AND c.TABLE_NAME <> 'flyway_schema_history' ORDER BY c.TABLE_NAME, c.ORDINAL_POSITION
    """), {"schema": schema}).mappings().all()
    if not tables or not columns:
        raise ValueError("application schema has no tables/columns to validate")
    failures = []
    for row in tables:
        reason = database_comment_problem(row["TABLE_NAME"], row["TABLE_COMMENT"])
        if reason:
            failures.append({"object": row["TABLE_NAME"], "reason": reason})
    for row in columns:
        reason = database_comment_problem(row["COLUMN_NAME"], row["COLUMN_COMMENT"])
        if reason:
            failures.append({"object": row["TABLE_NAME"] + "." + row["COLUMN_NAME"], "reason": reason})
    # 오류에는 소스 원문이나 COMMENT 내용을 담지 않는다. 의미의 정확성과 단위 설명은 독립 Review로 확인한다.
    return {"schema": schema, "table_count": len(tables), "column_count": len(columns), "failures": failures}


def allowed_ignored(name):
    path = Path(name)
    parts = path.parts
    if generated_output(name):
        return True
    if path.name == ".DS_Store" or path.name.endswith(".pyc"):
        return True
    if any(part in {".venv", "__pycache__", ".pytest_cache"} for part in parts):
        return True
    # IDE가 생성한 로컬 설정은 제외하되 같은 경로의 코드·보고서까지 숨기는 예외로 확장하지 않는다.
    if len(parts) >= 2 and parts[0] == ".idea":
        # EXCEPTION: IntelliJ DB introspection cache만 좁게 허용하며 실행 가능한 파일은 cache로 인정하지 않는다.
        if (len(parts) >= 5 and parts[1] == "dataSources" and "storage_v2" in parts[2:-1]
                and path.suffix == ".meta" and not os.access(ROOT / name, os.X_OK)):
            return True
        return path.suffix in {".xml", ".iml"} or path.name == ".gitignore"
    # 실제 credential은 제외하지만 변수 계약을 보여주는 example은 사용자가 Diff로 검토해야 한다.
    if len(parts) == 1 and (name == ".env" or name.startswith(".env.")) and name != ".env.example":
        return True
    # 서비스 V1 build 산출물·의존성 cache는 재생성 가능한 결과라 추적하지 않는다. 소스 디렉터리는 숨기지 않는다.
    if len(parts) >= 2 and (parts[0], parts[1]) in SERVICE_BUILD_OUTPUTS:
        return True
    if len(parts) >= 3 and parts[0] == "data" and parts[1] in {"raw", "downloaded", "parsed", "failed"}:
        # 원문 payload와 작업 산출물을 구분해 데이터 디렉터리에서도 규칙·코드·보고서는 숨기지 않는다.
        return path.suffix.lower() not in {".md", ".py", ".sh", ".yml", ".yaml"} and path.name != "README.md"
    return False


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
    untracked = [name for name in run("git", "ls-files", "--others", "--exclude-standard", "-z", capture=True).split("\0")
                 if name and not generated_output(name)]
    if untracked:
        raise ValueError("untracked project files:\n" + "\n".join(untracked))
    if any(not generated_output(name) for name in run("git", "diff", "--name-only", "--diff-filter=U", capture=True).splitlines()):
        raise ValueError("unresolved Git conflicts")
    indexed_new = set(run("git", "diff", "--cached", "--name-only", "--diff-filter=A", "-z", capture=True).split("\0"))
    unstaged = set(run("git", "diff", "--name-only", "-z", capture=True).split("\0"))
    if any(name and not generated_output(name) for name in indexed_new & unstaged):
        raise ValueError("new indexed files differ from working files; update their explicit Git entries")
    required = registry()["required_files"]
    # global ignore도 검사해 제어·설계·검증 입력이 Git 밖에 숨겨지는 것을 막는다.
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
        if name and not generated_output(name) and allowed_ignored(name):
            raise ValueError(f"raw/secret/cache must not be tracked: {name}")
    workspace_policy(registry())
    print("PASS: dev policy, tracked changes, ignore boundary, index visibility")
    run("git", "status", "--short", "--branch")


def has_korean(text):
    return bool(re.search(r"[가-힣]", text))


def c_style_comments(source, line_comments=True):
    """Java·TS·CSS 소스의 (줄 번호, 주석) 목록. 문자열 literal 안의 // 와 /* 는 주석으로 보지 않는다."""
    comments, index, line, quote = [], 0, 1, None
    while index < len(source):
        char = source[index]
        if quote:
            if char == "\\":
                index += 1
            elif char == quote:
                quote = None
            elif char == "\n" and quote != "`":
                quote = None
        elif char in "\"'`" and line_comments:
            quote = char
        elif source.startswith("/*", index):
            end = source.find("*/", index + 2)
            end = len(source) if end < 0 else end + 2
            comments.append((line, source[index:end]))
            line += source.count("\n", index, end)
            index = end
            continue
        elif line_comments and source.startswith("//", index):
            end = source.find("\n", index)
            end = len(source) if end < 0 else end
            comments.append((line, source[index:end]))
            index = end
            continue
        if source[index] == "\n":
            line += 1
        index += 1
    return comments


def comments_check():
    checked = 0
    for name in project_files():
        path = ROOT / name
        if name.endswith((".java", ".ts", ".tsx", ".css")):
            for line, text in c_style_comments(path.read_text(encoding="utf-8"), not name.endswith(".css")):
                # EXCEPTION: TypeScript triple-slash directive(/// <reference ...>)는 도구 지시문이라 설명성 주석이 아니다.
                if text.startswith("/// <reference"):
                    continue
                checked += 1
                if not has_korean(text):
                    raise ValueError(f"explanatory comment requires Korean: {name}:{line}")
        elif name.endswith(".py"):
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
        lexical = Path(os.path.abspath(path.parent / target))
        if lexical.is_relative_to(ROOT) and generated_output(lexical.relative_to(ROOT).as_posix()):
            # 생성 전의 출력 참조는 깨진 입력 링크가 아니다. 생성물의 symlink나 내용도 따라가지 않는다.
            continue
        destination = lexical.resolve()
        if not destination.is_relative_to(ROOT) or not destination.exists():
            raise ValueError(f"broken/outside documentation link: {path.relative_to(ROOT)} -> {target}")


def review_status(spec):
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
    integrity = "VERIFIED"
    for name, expected_hash in (
        (evidence, accepted["sha256"]),
        (accepted["reviewed_report"], accepted["reviewed_report_sha256"]),
    ):
        path = ROOT / name
        # 신뢰 판정은 생성물의 존재·Git 상태와 분리한다. 미검증이면 사람의 승인을 보류하며 build는 실패시키지 않는다.
        try:
            if path.is_symlink() or path.resolve() != path:
                integrity = "UNSAFE"
                break
            if not path.is_file():
                integrity = "UNAVAILABLE"
                break
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
        except (OSError, RuntimeError):
            integrity = "UNAVAILABLE"
            break
        if digest != expected_hash:
            integrity = "MISMATCH"
            break
    summary = f"AGY: recorded review_complete; recorded_result={accepted['result']}; reviewed_report={accepted['reviewed_report']}"
    summary += f"\nREVIEW EVIDENCE INTEGRITY: {integrity}; non-gating; human verification required"
    # 이전 Review를 이후 수정의 승인으로 오해하지 않도록 현재 보고서와 검토 대상의 범위를 구분한다.
    current = "complete" if integrity == "VERIFIED" and spec["report"] == accepted["reviewed_report"] else "pending"
    return summary + f"\nCURRENT REPORT REVIEW: {current}; human review PENDING"


def harness_check():
    spec = registry()
    actual = set(project_files())
    expected = set(spec["required_files"])
    workspace_policy(spec)
    if actual != expected:
        raise ValueError(f"Registry drift: missing={sorted(expected - actual)}, unregistered={sorted(actual - expected)}")
    if spec["phase"] not in ("phase0-preparation", *DATABASE_PHASES):
        raise ValueError("phase must reflect actual preparation")
    # 현재 Task의 공동 개발 Evidence가 과거 Report나 Reviewer 경로로 바뀌지 않도록 연결을 함께 검증한다.
    task = (ROOT / "harness/workspace/current-task.md").read_text(encoding="utf-8")
    final_reports = re.findall(r"\[Final Report\]\(([^)]+)\)", task)
    if len(final_reports) != 1 or Path(os.path.abspath(
        ROOT / "harness/workspace" / final_reports[0]
    )) != Path(os.path.abspath(ROOT / spec["report"])):
        raise ValueError("current-task Final Report differs from Registry report")
    if not isinstance(spec["report"], str) or workspace_category(spec["report"]) != "GENERATED_REPORT":
        raise ValueError("current-task report reference must name a generated Report")
    if not spec["report"].startswith(TASK_OUTPUT_PATHS["development"]["reports"]):
        raise ValueError("current-task report must use shared development path")
    status = review_status(spec)
    if spec["branches"] != {"development": "dev", "verified": "main", "deployment": "prod"}:
        raise ValueError("branch policy drift")
    for name in actual:
        path = ROOT / name
        if not path.is_file():
            raise ValueError(f"missing registered file: {name}")
        if workspace_category(name) in STATIC_WORKSPACE_FILES and (path.is_symlink() or path.resolve() != path):
            raise ValueError(f"unsafe static Workspace anchor: {name}")
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
    if any((ROOT / name).exists() for name in spec["forbidden_top_level_modules"]):
        raise ValueError("forbidden top-level product module added; use the registered product boundary")
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
    print("PASS: static docs/links, Skills/Rules Registry, commands, phase, Compose/CI and workspace control; outputs non-gating")
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
