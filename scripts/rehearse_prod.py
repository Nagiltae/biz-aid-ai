"""격리된 운영 리허설. 기존 실행 컨테이너의 process 설정을 내부 재사용하며 Secret 파일·값은 열거나 출력하지 않는다.

WHY: 운영 Compose를 그대로 사용하되 DB·Qdrant·계정·volume은 별도 프로젝트로 분리한다.
AWS 임시 인증은 SDK credential chain에서 process로만 전달하고 파일에 저장하지 않는다.
"""
import argparse
import concurrent.futures
import json
import os
import re
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import threading
import time

import requests

ROOT = Path(__file__).resolve().parents[1]
PROJECT = "bizaid-rehearsal52"
EVIDENCE = ROOT / "harness/workspace/artifacts/development/bundle5-2-predeploy"


def command(args, *, env=None, stdin=None, timeout=1200):
    result = subprocess.run(args, input=stdin, capture_output=True, env=env, cwd=ROOT, timeout=timeout)
    if result.returncode:
        # BOUNDARY: Docker 오류는 설정값을 반사할 수 있다. 원문을 출력하지 않는다.
        raise RuntimeError(f"command_failed:{args[0]}:{result.returncode}")
    return result.stdout


def running_environment(name):
    raw = command(["docker", "inspect", "--format", "{{json .Config.Env}}", name])
    # process 간 내부 전달만 한다. 이 dict는 로그·Report·임시 파일에 쓰지 않는다.
    return dict(item.split("=", 1) for item in json.loads(raw) if "=" in item)


def request(base, path, method="GET", token=None, **options):
    headers = {"Authorization": "Bearer " + token} if token else {}
    started = time.monotonic()
    response = requests.request(method, base + path, headers=headers, timeout=110, **options)
    if not response.ok:
        raise RuntimeError(f"http_failed:{path}:{response.status_code}")
    return response, round(time.monotonic() - started, 3)


def sql(container, query):
    return command(["docker", "exec", "-i", container, "sh", "-c",
                    'MYSQL_PWD="$MYSQL_PASSWORD" exec mysql -N -B -u "$MYSQL_USER" "$MYSQL_DATABASE"'], stdin=query.encode() if isinstance(query, str) else query)


def image_settings(repository, tags, platform):
    if not repository or not re.fullmatch(r"[a-z0-9][a-z0-9._:/-]*", repository):
        raise ValueError("image_repository_required")
    for service in ("frontend", "backend", "fastapi"):
        tag = tags.get(service)
        if not tag or not re.fullmatch(r"[a-zA-Z0-9_][a-zA-Z0-9_.-]{0,127}", tag):
            raise ValueError(f"{service}_image_tag_required")
    if platform not in {"linux/amd64", "linux/arm64"}:
        raise ValueError("unsupported_image_platform")
    return {"BIZAID_IMAGE_REPO": repository, "BIZAID_IMAGE_PLATFORM": platform,
            **{f"BIZAID_{service.upper()}_TAG": tags[service] for service in ("frontend", "backend", "fastapi")}}


def rehearsal(repository, tags, platform):
    images = image_settings(repository, tags, platform)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    if command(["docker", "ps", "-aq", "--filter", "label=com.docker.compose.project=" + PROJECT]).strip():
        raise RuntimeError("existing_rehearsal_requires_manual_review")
    env = dict(os.environ, **images)
    source = running_environment("biz-aid-ai-backend-1")
    env.update({key: source[key] for key in ("MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE", "JWT_SECRET", "INTERNAL_AI_API_KEY")})
    original_db = env["MYSQL_DATABASE"]
    collections = requests.get("http://127.0.0.1:6333/collections", timeout=10).json()["result"]["collections"]
    names = [row["name"] for row in collections if row["name"].startswith("bizaid_v2_")]
    if len(names) != 1:
        raise RuntimeError("v2_collection_selection_ambiguous")
    name = names[0]
    count = requests.post(f"http://127.0.0.1:6333/collections/{name}/points/count", json={"exact": True}, timeout=15).json()["result"]["count"]
    # 인증을 요청하는 것은 SDK다. Agent는 ~/.aws 파일의 내용을 직접 읽지 않는다.
    import boto3
    creds = boto3.Session(profile_name="bizaid-dev").get_credentials().get_frozen_credentials()
    env.update(REHEARSAL_AWS_ACCESS_KEY_ID=creds.access_key, REHEARSAL_AWS_SECRET_ACCESS_KEY=creds.secret_key,
               REHEARSAL_AWS_SESSION_TOKEN=creds.token or "")
    env.update(COMPOSE_DISABLE_ENV_FILE="1", MYSQL_HOST="rehearsal-mysql", MYSQL_PORT="3306", MYSQL_DATABASE="bizaid_rehearsal52",
               MYSQL_SSL_MODE="DISABLED", BIZAID_MODEL_PATH=os.environ.get("BIZAID_DOCLING_ARTIFACTS_PATH", str(Path.home()/".cache/biz-aid/docling-artifacts")),
               MYSQL_TLS_CERTS_PATH="/tmp", QDRANT_COLLECTION=name, CADDY_SITE="localhost:80",
               CADDY_HTTP_BIND="127.0.0.1:18080", CADDY_HTTPS_BIND="127.0.0.1:18443", FASTAPI_WORKERS="1")
    # 전체 리허설 상한 40회는 임시 런타임 계측으로 enforced한다. 제품 provider·prompt는 바꾸지 않는다.
    prior = EVIDENCE/"bedrock-call-count.json"
    env["REHEARSAL_PRIOR_CALLS"] = str(json.loads(prior.read_text())["attempted_calls"] if prior.exists() else 0)
    runner = '''import json,threading
from pathlib import Path
from biz_aid_pipeline.rag.llm import BedrockLlmProvider
path=Path('/tmp/bedrock-call-count.json')
lock=threading.Lock()
original=BedrockLlmProvider._client
count=int(__import__("os").environ.get("REHEARSAL_PRIOR_CALLS", "0"))
def before(**kwargs):
    global count
    with lock:
        if count>=40: raise RuntimeError('rehearsal_bedrock_budget_exhausted')
        count+=1
        path.write_text(json.dumps({'attempted_calls':count,'limit':40}))
def client(self):
    result=original(self)
    if not getattr(self,'_rehearsal_metered',False):
        result.meta.events.register('before-call.bedrock-runtime.ConverseStream',before)
        self._rehearsal_metered=True
    return result
BedrockLlmProvider._client=client
import uvicorn
uvicorn.run('biz_aid_pipeline.api.app:app',host='0.0.0.0',port=8000,access_log=False)
'''
    result = {"status": "IN_PROGRESS", "original_collection": name, "original_point_count": count, "workers": 1,
              "source_database": original_db, "aws_budget": 40, "images": images,
              "permission_limit": "macOS Docker Desktop은 Ubuntu 서버의 파일 권한을 재현하지 않음"}
    with tempfile.TemporaryDirectory(prefix="bizaid-rehearsal52-") as tmp:
        tmp = Path(tmp)
        (tmp/"certs").mkdir()
        env["MYSQL_TLS_CERTS_PATH"] = str(tmp/"certs")
        (tmp/"entry.py").write_text(runner)
        # 임시 코드·설정에는 Secret 값이 없다. 환경변수 이름만 참조한다.
        overlay = {"services": {
            "rehearsal-mysql": {"image": "mysql:8.4", "environment": {"MYSQL_DATABASE": "${MYSQL_DATABASE}", "MYSQL_USER": "${MYSQL_USER}",
                                  "MYSQL_PASSWORD": "${MYSQL_PASSWORD}", "MYSQL_ROOT_PASSWORD": "${MYSQL_PASSWORD}"},
                                  "networks": ["service"], "volumes": ["rehearsal_mysql:/var/lib/mysql"]},
            "qdrant": {"ports": ["127.0.0.1:16333:6333"]},
            "backend": {"image": f"{repository}:backend-{tags['backend']}", "platform": platform, "pull_policy": "never", "depends_on": ["rehearsal-mysql", "fastapi"]},
            "frontend": {"image": f"{repository}:frontend-{tags['frontend']}", "platform": platform, "pull_policy": "never"},
            "fastapi": {"image": f"{repository}:fastapi-{tags['fastapi']}", "platform": platform, "pull_policy": "never", "command": ["python", "/rehearsal/entry.py"],
                        "environment": {"AWS_ACCESS_KEY_ID": "${REHEARSAL_AWS_ACCESS_KEY_ID}", "AWS_SECRET_ACCESS_KEY": "${REHEARSAL_AWS_SECRET_ACCESS_KEY}",
                                        "AWS_SESSION_TOKEN": "${REHEARSAL_AWS_SESSION_TOKEN}", "REHEARSAL_PRIOR_CALLS": "${REHEARSAL_PRIOR_CALLS}"},
                        "volumes": [f"{tmp}:/rehearsal:ro"]}}, "volumes": {"rehearsal_mysql": {}}}
        overlay_path = tmp/"override.json"
        overlay_path.write_text(json.dumps(overlay))
        # BOUNDARY: 선택한 기존 이미지만 실행한다. 소스 build override와 과거 ARM 이미지 이름은 사용하지 않는다.
        compose = ["docker", "compose", "--env-file", os.devnull, "-p", PROJECT, "-f", "docker-compose.prod.yml", "-f", str(overlay_path)]
        mysql = PROJECT + "-rehearsal-mysql-1"
        try:
            command(compose + ["up", "-d", "--no-build", "rehearsal-mysql", "qdrant"], env=env)
            for _ in range(60):
                try:
                    sql(mysql, "SELECT 1;")
                    break
                except RuntimeError:
                    time.sleep(1)
            else:
                raise RuntimeError("rehearsal_mysql_not_ready")
            # Flyway 계보는 공통 migration을 쓰되 이력은 새로운 DB에서 새로 만든다.
            command(["docker", "run", "--rm", "--network", PROJECT+"_service", "-v", str(ROOT/"migrations")+":/flyway/sql:ro",
                     "-e", "FLYWAY_PASSWORD", "redgate/flyway:11", "-url=jdbc:mysql://rehearsal-mysql:3306/bizaid_rehearsal52?allowPublicKeyRetrieval=true&useSSL=false",
                     "-user="+env["MYSQL_USER"], "migrate"], env=dict(env, FLYWAY_PASSWORD=env["MYSQL_PASSWORD"]))
            dump = tmp/"programs.sql"
            command(["scripts/export_program_data.sh", "biz-aid-ai-mysql-1", str(dump)])
            sql(mysql, dump.read_bytes())
            snapshot = tmp/"v2.snapshot"
            command(["scripts/snapshot_v2_qdrant.sh", "http://127.0.0.1:6333", name, str(snapshot)])
            with snapshot.open("rb") as handle:
                response = requests.post(f"http://127.0.0.1:16333/collections/{name}/snapshots/upload?priority=snapshot", files={"snapshot": handle}, timeout=300)
                response.raise_for_status()
            restored = requests.post(f"http://127.0.0.1:16333/collections/{name}/points/count", json={"exact": True}, timeout=30).json()["result"]["count"]
            tables = ("support_programs", "support_program_sync_history", "document_acquisition_runs", "document_sources", "document_parse_results", "document_archive_members")
            counts = {}
            for table in tables:
                original = int(sql("biz-aid-ai-mysql-1", "SELECT COUNT(*) FROM " + table + ";").strip())
                actual = int(sql(mysql, "SELECT COUNT(*) FROM " + table + ";").strip())
                if actual != original: raise RuntimeError("rehearsal_table_count_mismatch:" + table)
                counts[table] = {"original": original, "restored": actual}
            if restored != count: raise RuntimeError("rehearsal_qdrant_count_mismatch")
            result["data_move"] = {"tables": counts, "dump_bytes": dump.stat().st_size, "snapshot_bytes": snapshot.stat().st_size,
                                   "restored_points": restored, "user_rows_before_smoke": int(sql(mysql, "SELECT COUNT(*) FROM users;").strip())}
            command(compose + ["up", "-d", "--no-build", "caddy", "frontend", "backend", "fastapi"], env=env)
            base = "http://localhost:18080"
            for _ in range(120):
                try:
                    response = requests.get(base+"/api/health", timeout=2)
                    if response.ok: break
                except requests.RequestException: pass
                time.sleep(1)
            else: raise RuntimeError("rehearsal_backend_not_ready")
            response, _ = request(base, "/")
            assert 'id="root"' in response.text
            for header in ("X-Frame-Options", "X-Content-Type-Options", "Referrer-Policy", "Strict-Transport-Security"):
                if header not in response.headers: raise RuntimeError("missing_security_header:" + header)
            trial, _ = request(base, "/api/auth/trial", "POST")
            token = trial.json()["accessToken"]
            question, seconds = request(base, "/api/ai/query", "POST", token, json={"query": "소상공인 금융 지원사업 찾아줘"})
            result["question"] = {"status": question.json()["result"]["status"], "seconds": seconds}
            workflow, seconds = request(base, "/api/ai/workflows", "POST", token, json={"query": "경기도 소상공인 금융 지원사업 추천"})
            state = workflow.json()
            steps = [{"status": state["status"], "seconds": seconds}]
            # 최대 Top3의 기존 continue 단계만 따른다. 추가 질문 답변·재판정은 하지 않는다.
            for _ in range(5):
                if state["nextAction"] != "CONTINUE": break
                workflow, seconds = request(base, f'/api/ai/workflows/{state["workflowId"]}/continue', "POST", token)
                state = workflow.json()
                steps.append({"status": state["status"], "seconds": seconds})
            result["recommendation"] = {"steps": steps, "status": state["status"], "progress": state.get("progress")}
            # 동시 5명·10명. 각 사용자 별도 체험 계정, 질문은 SEARCH_LIST라 생성 호출은 보통 1회다.
            concurrency = []
            for n in (5, 10):
                tokens = [request(base, "/api/auth/trial", "POST")[0].json()["accessToken"] for _ in range(n)]
                samples, stop = [], threading.Event()
                def sample():
                    while not stop.is_set():
                        samples.append(command(["docker", "stats", "--no-stream", "--format", "{{json .}}",
                                                PROJECT+"-fastapi-1", PROJECT+"-backend-1"], timeout=15).decode())
                        stop.wait(.5)
                monitor = threading.Thread(target=sample)
                monitor.start()
                def query(current):
                    reply, elapsed = request(base, "/api/ai/query", "POST", current, json={"query": "소상공인 지원사업 찾아줘"})
                    return {"status": reply.json()["result"]["status"], "seconds": elapsed}
                try:
                    with concurrent.futures.ThreadPoolExecutor(max_workers=n) as pool:
                        outputs = list(pool.map(query, tokens))
                finally:
                    stop.set()
                    monitor.join()
                latencies = [item["seconds"] for item in outputs]
                concurrency.append({"users": n, "results": outputs, "median_seconds": statistics.median(latencies),
                                    "max_seconds": max(latencies), "resource_samples": [json.loads(line) for sample in samples for line in sample.splitlines()]})
            result["concurrency"] = concurrency
            # 배포 후 점검 스크립트도 같은 리허설에 정확히 한 번 실행한다.
            result["smoke_prod"] = json.loads(command(["scripts/smoke_prod.sh", base], timeout=150))
            result["bedrock"] = json.loads(command(["docker", "exec", PROJECT+"-fastapi-1", "cat", "/tmp/bedrock-call-count.json"]))
            result["status"] = "PASS"
        except Exception as error:
            result["status"] = "BLOCKED_OR_FAILED"
            result["error_type"] = type(error).__name__
            if isinstance(error, RuntimeError): result["error_code"] = str(error)
            raise
        finally:
            # BOUNDARY: 삭제하는 것은 이름·설정이 고정된 리허설 프로젝트 volume뿐이다. dev 프로젝트에 down을 실행하지 않는다.
            try:
                metered = json.loads(command(["docker", "exec", PROJECT+"-fastapi-1", "cat", "/tmp/bedrock-call-count.json"]))
                (EVIDENCE/"bedrock-call-count.json").write_text(json.dumps(metered, indent=2)+"\n")
                result["bedrock"] = metered
            except Exception:
                pass
            command(compose + ["down", "--volumes", "--remove-orphans"], env=env)
            result["rehearsal_cleanup"] = "DONE"
            (EVIDENCE/"rehearsal-results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="운영 Compose 로컬 리허설(실제 Bedrock 최대40회·별도 DB·volume)")
    parser.add_argument("--execute", action="store_true", required=True)
    parser.add_argument("--image-repo", default=os.environ.get("BIZAID_IMAGE_REPO"))
    parser.add_argument("--frontend-tag", default=os.environ.get("BIZAID_FRONTEND_TAG"))
    parser.add_argument("--backend-tag", default=os.environ.get("BIZAID_BACKEND_TAG"))
    parser.add_argument("--fastapi-tag", default=os.environ.get("BIZAID_FASTAPI_TAG"))
    parser.add_argument("--platform", default=os.environ.get("BIZAID_IMAGE_PLATFORM", "linux/amd64"))
    args = parser.parse_args()
    try:
        result = rehearsal(args.image_repo, {"frontend": args.frontend_tag, "backend": args.backend_tag,
                                            "fastapi": args.fastapi_tag}, args.platform)
        print(json.dumps({"status": result["status"], "bedrock": result.get("bedrock"), "evidence": str(EVIDENCE)}, ensure_ascii=False))
    except Exception as error:
        print("rehearsal_failed:"+type(error).__name__, file=sys.stderr)
        sys.exit(1)
