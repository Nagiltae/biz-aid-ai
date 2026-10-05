#!/usr/bin/env bash
# BOUNDARY: 서버에서 고정 버전 이미지만 실행한다. 비밀값을 해석·출력하거나 build·Git 작업을 하지 않는다.
# WHY: 설정의 나머지 바이트를 보존하고 원자적으로 교체하기 위해 Ubuntu의 기본 Python 3를 사용한다.
set -euo pipefail
command -v python3 >/dev/null 2>&1 || { echo 'FAIL: Python 3가 필요합니다.' >&2; exit 1; }
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
exec python3 - "$ROOT" "$@" <<'PY'
import datetime
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(sys.argv[1])
SERVICES = ("frontend", "backend", "fastapi")
KEYS = {s: "BIZAID_" + s.upper() + "_TAG" for s in SERVICES}
PUBLIC = {"BIZAID_IMAGE_REPO", "CADDY_SITE", *KEYS.values()}
ENV = ROOT / ".env.prod"
HISTORY = ROOT / "deploy-history.log"
LOCK = ROOT / ".deploy.lock"
COMPOSE = ["docker", "compose", "--env-file", str(ENV), "-f", str(ROOT / "docker-compose.prod.yml")]
PROCESS = {k: v for k, v in os.environ.items() if k not in PUBLIC | {"BIZAID_IMAGE_PLATFORM"}}
PROCESS["COMPOSE_DISABLE_ENV_FILE"] = "1"


class DeployError(Exception):
    """원문 설정·외부 명령 출력을 포함하지 않는 사용자 안내 오류다."""


def fail(message):
    raise DeployError(message)


def arguments(args):
    if args == ["status"]:
        return "status", {}
    mode = "deploy"
    if args[:1] == ["--rollback"]:
        mode, args = "rollback", args[1:]
    if not args:
        fail("사용법: bash scripts/deploy.sh <서비스...> / 서비스=버전 / --rollback <서비스...> / status")
    selected = {}
    for arg in args:
        service, separator, tag = arg.partition("=")
        if service not in SERVICES or service in selected or (separator and (mode == "rollback" or not valid_tag(tag))):
            fail("서비스는 frontend/backend/fastapi를 중복 없이 지정하세요. 명시 태그는 서비스=버전 형식입니다.")
        selected[service] = tag if separator else None
    return mode, selected


def valid_tag(tag):
    return bool(tag and tag != "latest" and re.fullmatch(r"[a-zA-Z0-9_][a-zA-Z0-9_.-]{0,100}", tag))


def public_values():
    if ENV.is_symlink() or not ENV.is_file():
        fail("서버 폴더에 일반 파일 .env.prod가 필요합니다.")
    values = {}
    # BOUNDARY: 저장소·서비스 태그·도메인만 해석한다. 다른 설정 줄의 값은 디코딩하거나 셸로 실행하지 않는다.
    with ENV.open("rb") as stream:
        for line in stream:
            match = re.match(rb"\s*(?:export\s+)?([A-Z_0-9]+)\s*=", line)
            if not match:
                continue
            key = match[1].decode("ascii")
            if key not in PUBLIC:
                continue
            if key in values:
                fail("공개 설정 줄이 중복되었습니다: " + key)
            value = line[match.end():].decode("utf-8").strip()
            quoted = re.fullmatch(r"(['\"])(.*?)\1(?:\s*#.*)?", value)
            if quoted:
                value = quoted[2]
            else:
                value = re.split(r"\s+#", value, maxsplit=1)[0].strip()
            values[key] = value
    for key in KEYS.values():
        if values.get(key) and not valid_tag(values[key]):
            fail("서비스 태그 형식을 확인하세요: " + key)
    return values


def run(args, reason, check=True):
    try:
        result = subprocess.run(args, cwd=ROOT, env=PROCESS, capture_output=True, text=True)
    except OSError:
        fail(reason + " (명령 실행 불가, 원문 출력 안 함)")
    if check and result.returncode:
        fail(reason + " (로그인·권한·설정·연결 확인, 원문 출력 안 함)")
    return result


def image_rows():
    raw = run(COMPOSE + ["ps", "--all", "--format", "json"], "컨테이너 상태 확인 실패").stdout.strip()
    if not raw:
        return []
    try:
        try:
            parsed = json.loads(raw)
            rows = parsed if isinstance(parsed, list) else [parsed]
        except json.JSONDecodeError:
            rows = [json.loads(line) for line in raw.splitlines()]
        if not all(isinstance(r, dict) for r in rows):
            raise ValueError()
        return rows
    except (ValueError, TypeError):
        fail("컨테이너 상태 응답 형식을 확인할 수 없습니다(원문 출력 안 함).")


def show_status(values):
    rows = image_rows()
    print("서비스 | 설정 태그 | 실행 중 컨테이너 이미지")
    for service in SERVICES:
        images = [r.get("Image", "") for r in rows if r.get("Service") == service and r.get("State") == "running"]
        safe = [i for i in images if isinstance(i, str) and re.fullmatch(r"[a-zA-Z0-9._/:-]+", i)]
        print(service + " | " + (values.get(KEYS[service]) or "없음") + " | " + (", ".join(safe) or "실행 중 없음"))


def prior_tags(selected, values):
    if HISTORY.is_symlink() or not HISTORY.is_file():
        fail("되돌릴 기록이 없습니다. 서비스=이전버전 형식으로 지정하세요.")
    records = []
    for line in HISTORY.read_text().splitlines():
        fields = line.split("\t")
        if len(fields) != 4 or fields[1] not in SERVICES or not valid_tag(fields[3]) or (fields[2] != "-" and not valid_tag(fields[2])):
            fail("deploy-history.log 형식을 확인하세요(원문 출력 안 함).")
        records.append(fields)
    targets = {}
    for service in selected:
        current = values.get(KEYS[service], "")
        previous = next((old for _, name, old, new in reversed(records) if name == service and new == current and old != new), None)
        if not previous or previous == "-":
            fail(service + ": 현재 태그에 대응하는 이전 버전 기록이 없습니다. 서비스=이전버전 형식으로 지정하세요.")
        targets[service] = previous
    return targets


def latest_tag(repository, service):
    image = repository + ":" + service + "-latest"
    run(["docker", "pull", "--platform", "linux/amd64", image], service + ": latest pull 실패. 첫 배포는 서비스=버전으로 지정할 수 있습니다.")
    result = run(["docker", "image", "inspect", "--format", '{{index .Config.Labels "org.bizaid.release-tag"}}', image], service + ": 릴리스 라벨 조회 실패")
    tag = result.stdout.strip()
    if not valid_tag(tag):
        fail(service + ": latest에 올바른 릴리스 라벨이 없습니다. 서비스=버전으로 지정하세요.")
    return tag


def backup_and_replace(targets, stamp):
    # WHY: 시각이 같은 작업도 기존 백업을 덮지 않는다. 설정 전체는 그대로 복사하고 태그 줄만 교체한다.
    backup = ROOT / (".env.prod.backup-" + stamp + "-" + str(os.getpid()))
    if ENV.is_symlink() or HISTORY.is_symlink():
        fail("설정·기록 파일의 심볼릭 링크는 사용하지 않습니다.")
    os.chmod(ENV, 0o600)
    backup_fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with ENV.open("rb") as original, os.fdopen(backup_fd, "wb") as saved:
        shutil.copyfileobj(original, saved)
        saved.flush()
        os.fsync(saved.fileno())
    original = ENV.read_bytes()
    wanted = {KEYS[s].encode(): tag.encode() for s, tag in targets.items()}
    seen = set()
    lines = []
    for line in original.splitlines(keepends=True):
        match = re.match(rb"\s*(?:export\s+)?([A-Z_0-9]+)\s*=", line)
        if match and match[1] in wanted:
            key = match[1]
            newline = b"\r\n" if line.endswith(b"\r\n") else b"\n"
            lines.append(key + b"=" + wanted[key] + newline)
            seen.add(key)
        else:
            lines.append(line)
    result = b"".join(lines)
    for key, tag in wanted.items():
        if key not in seen:
            if result and not result.endswith(b"\n"):
                result += b"\n"
            result += key + b"=" + tag + b"\n"
    fd, temporary = tempfile.mkstemp(prefix=".env.prod.edit-", dir=ROOT)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.chmod(temporary, 0o600)
            stream.write(result)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, ENV)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return backup.name


def history(changes, stamp):
    fd = os.open(HISTORY, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as stream:
        os.fchmod(stream.fileno(), 0o600)
        for service, (old, new) in changes.items():
            stream.write("\t".join((stamp, service, old or "-", new)) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def summary(changes):
    print("서비스 | 이전 | 지금 | 되돌리는 명령")
    for service, (old, new) in changes.items():
        rollback = "bash scripts/deploy.sh " + service + "=" + old if old else "이전 태그 없음; 백업 확인"
        print(" | ".join((service, old or "없음", new, rollback)))


def rollback_command(changes):
    args = [s + "=" + old for s, (old, _) in changes.items() if old]
    if args:
        print("되돌리기: bash scripts/deploy.sh " + " ".join(args), file=sys.stderr)


def check_running(changes, repository):
    rows = image_rows()
    for service, (_, tag) in changes.items():
        selected = [r for r in rows if r.get("Service") == service]
        image = repository + ":" + service + "-" + tag
        if not selected or any(r.get("State") != "running" or r.get("Image") != image or r.get("Health") == "unhealthy" for r in selected):
            fail(service + ": 요청한 고정 버전 컨테이너가 정상 실행 중인지 확인하지 못했습니다.")


def smoke(site, changes):
    url = "https://" + site
    # WHY: 앱 시작 직후의 준비 시간을 기다린다. 체험 계정·AI 질문을 만드는 smoke는 한 번만 실행한다.
    if "fastapi" in changes:
        check = "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/health', timeout=5).close()"
        for attempt in range(30):
            ready = run(COMPOSE + ["exec", "-T", "fastapi", "python", "-c", check], "FastAPI 준비 확인 실패", check=False)
            if ready.returncode == 0:
                break
            if attempt == 29:
                fail("FastAPI 준비 시간 초과. smoke는 실행하지 않았습니다.")
            time.sleep(3)
    for attempt in range(30):
        health = run(["curl", "--fail", "--silent", "--max-time", "5", url + "/api/health"], "health 준비 확인 실패", check=False)
        if health.returncode == 0:
            break
        if attempt == 29:
            fail("health 준비 시간 초과: " + url + "/api/health. smoke는 실행하지 않았습니다.")
        time.sleep(3)
    result = run(["bash", str(ROOT / "scripts/smoke_prod.sh"), url], "smoke 실행 실패", check=False)
    if result.returncode:
        detail = ""
        for line in (result.stderr + "\n" + result.stdout).splitlines():
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if not isinstance(record, dict):
                continue
            stage = record.get("stage")
            reason = record.get("reason")
            status = record.get("http_status")
            if stage in {"health", "landing", "trial", "ai_query", "usage"}:
                detail += " stage=" + stage
            if isinstance(status, int) and 100 <= status <= 599:
                detail += " http_status=" + str(status)
            if isinstance(reason, str) and re.fullmatch(r"[A-Za-z_]{1,60}", reason):
                detail += " reason=" + reason
        fail("smoke 점검 실패:" + url + detail + " (응답·토큰 원문 출력 안 함)")
    print("점검 PASS: " + url)


def main():
    mode, selected = arguments(sys.argv[2:])
    if not shutil.which("docker"):
        fail("Docker가 없습니다.")
    if mode == "status":
        show_status(public_values())
        return
    try:
        LOCK.mkdir(mode=0o700)
    except FileExistsError:
        fail("다른 배포가 진행 중이거나 .deploy.lock이 남아 있습니다. 실행 중인 작업부터 확인하세요.")
    changes = {}
    written = False
    try:
        values = public_values()
        repository = values.get("BIZAID_IMAGE_REPO", "")
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*/[a-z0-9][a-z0-9_.-]*", repository):
            fail(".env.prod의 BIZAID_IMAGE_REPO를 확인하세요(값 출력 안 함).")
        site = values.get("CADDY_SITE") or "biz-aid.cloud"
        if not re.fullmatch(r"(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", site):
            fail("CADDY_SITE에는 대표 도메인만 지정하세요(값 출력 안 함).")
        if HISTORY.is_symlink():
            fail("deploy-history.log의 심볼릭 링크는 사용하지 않습니다.")
        targets = prior_tags(selected, values) if mode == "rollback" else {
            s: tag if tag is not None else latest_tag(repository, s) for s, tag in selected.items()}
        for service, tag in targets.items():
            old = values.get(KEYS[service], "")
            if tag == old:
                print(service + ": 이미 최신 (" + tag + "), 건너뜀")
            else:
                changes[service] = (old, tag)
        if not changes:
            print("서비스 | 이전 | 지금 | 되돌리는 명령")
            for service in selected:
                tag = values.get(KEYS[service]) or "없음"
                print(service + " | " + tag + " | " + tag + " | 변경 없음")
            return
        if not shutil.which("curl"):
            fail("HTTPS 준비 확인을 위한 curl이 필요합니다.")
        stamp = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).strftime("%Y%m%d-%H%M%S-%f")
        backup = backup_and_replace({s: new for s, (_, new) in changes.items()}, stamp)
        written = True
        print("설정 백업: " + backup + " (600)")
        history(changes, stamp)
        run(COMPOSE + ["config", "--quiet"], "Compose config 검사 실패")
        run(COMPOSE + ["pull", *changes], "고정 버전 이미지 pull 실패")
        run(COMPOSE + ["up", "-d", "--no-deps", *changes], "컨테이너 적용 실패")
        check_running(changes, repository)
        smoke(site, changes)
        summary(changes)
    except (DeployError, OSError, UnicodeError, KeyboardInterrupt) as error:
        if written:
            print("설정은 새 태그로 기록되어 있습니다. 자동으로 되돌리지 않습니다.", file=sys.stderr)
            summary(changes)
            rollback_command(changes)
        if isinstance(error, DeployError):
            raise
        fail("배포 중 파일 처리·중단 오류가 발생했습니다(원문 출력 안 함).")
    finally:
        LOCK.rmdir()


try:
    main()
except DeployError as error:
    print("FAIL: " + str(error), file=sys.stderr)
    sys.exit(1)
PY
