import os
import json
import socket
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data-pipeline/src"))
from biz_aid_pipeline.config.settings import DbConfig, PipelineError, profile_values


def configuration(root, environ=None):
    names = {"MYSQL_HOST", "MYSQL_PORT", "MYSQL_DATABASE", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_ROOT_PASSWORD"}
    db = DbConfig.load(root, "dev", environ)
    config = profile_values(root, "dev", names, environ)
    if not config.get("MYSQL_ROOT_PASSWORD"):
        raise PipelineError("dev_database_configuration_required:MYSQL_ROOT_PASSWORD")
    config.update(MYSQL_HOST=db.host, MYSQL_PORT=str(db.port), MYSQL_DATABASE=db.database, MYSQL_USER=db.user)
    return config


def compose_command(root):
    # 명시한 Profile 파일이 없어도 OS 주입은 사용하되 generic .env로 보완하지 않는다.
    path = root / ".env.dev"
    return ["docker", "compose", "--env-file", str(path) if path.is_file() else os.devnull,
            "--project-name", "biz-aid-ai", "-f", str(root / "docker-compose.yml"), "--profile", "dev-db"]


def port_available(command, root, env):
    result = subprocess.run(command + ["ps", "-q", "mysql"], cwd=root, env=env, capture_output=True)
    if result.returncode:
        raise PipelineError("dev_mysql_inspection_failed")
    identifier = result.stdout.decode().strip()
    if identifier:
        result = subprocess.run(["docker", "inspect", identifier], cwd=root, env=env, capture_output=True)
        if result.returncode:
            raise PipelineError("dev_mysql_inspection_failed")
        container = json.loads(result.stdout)[0]
        mappings = container["NetworkSettings"]["Ports"].get("3306/tcp") or []
        if container["State"]["Running"] and any(p["HostIp"] == "127.0.0.1" and p["HostPort"] == "3306" for p in mappings):
            return
    # 다른 서비스를 자동으로 종료하지 않도록 Host 충돌 시 기동 전에 실패한다. 컨테이너 내부 포트는 대상이 아니다.
    try:
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 3306))
    except OSError:
        raise PipelineError("host_3306_in_use_user_approval_required") from None


def sanitized_output(raw, config):
    # Docker가 인증정보를 반사할 수 있으므로 원본 예외나 출력을 로그에도 남기지 않는다.
    for name in ("MYSQL_PASSWORD", "MYSQL_ROOT_PASSWORD"):
        secret = config[name]
        if any(token.encode() in raw for token in (secret, quote(secret, safe=""), json.dumps(secret)[1:-1])):
            return b"[REDACTED: credential reflected; entire command output withheld]\n"
    return raw


def prepare(root=ROOT, environ=None):
    config = configuration(root, environ)
    env = dict(os.environ if environ is None else environ, **config, COMPOSE_DISABLE_ENV_FILE="1")
    command = compose_command(root)
    port_available(command, root, env)
    log = root / "harness/workspace/artifacts/codex/infra-dev-mysql/logs/preparation.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("ab") as output:
        for args, database in ((["up", "-d", "--wait", "--wait-timeout", "180", "mysql"], None),
                # Unix socket의 root@localhost와 TCP 계정은 인증값이 다를 수 있어 검증된 로컬 TCP로 연결한다.
                (["exec", "-T", "mysql", "sh", "-c", 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -h127.0.0.1 --protocol=TCP'], "test_permissions"),
                (["run", "--rm", "flyway", "migrate"], "biz_aid_dev"),
                (["run", "--rm", "flyway", "validate"], "biz_aid_dev"),
                (["run", "--rm", "flyway", "migrate"], "biz_aid_test"),
                (["run", "--rm", "flyway", "validate"], "biz_aid_test")):
            query = None
            if database == "test_permissions":
                # 테스트 DB 권한만 기존 사용자에게 부여한다. 사용자 계정 생성·비밀번호 변경·데이터 삭제는 하지 않는다.
                user = config["MYSQL_USER"].replace("\\", "\\\\").replace("'", "''")
                query = ("CREATE DATABASE IF NOT EXISTS biz_aid_test CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;\n"
                         f"GRANT ALL PRIVILEGES ON biz_aid_test.* TO '{user}'@'%';\n").encode()
            elif database:
                env["FLYWAY_URL"] = f"jdbc:mysql://mysql:3306/{database}?allowPublicKeyRetrieval=true&useSSL=false"
            result = subprocess.run(command + args, cwd=root, env=env, capture_output=True, input=query)
            if result.returncode:
                # 실패한 Docker 출력에는 선택하지 않은 API 설정값도 섞일 수 있어 전체 출력을 보존하지 않는다.
                output.write(f"command failed (exit {result.returncode}); output withheld\n".encode())
                raise PipelineError("dev_mysql_bootstrap_failed_see_sanitized_log")
            output.write(sanitized_output(result.stdout + result.stderr, config))
    print("PASS: dev MySQL ready; common Flyway migrate/validate dev and test; secrets excluded")


if __name__ == "__main__":
    try:
        prepare()
    except PipelineError as error:
        print("FAIL: " + str(error) + "; inspect sanitized env-port-mysql.log if created", file=sys.stderr)
        sys.exit(1)
    except (ValueError, OSError):
        print("FAIL: dev MySQL setup; inspect sanitized env-port-mysql.log if created", file=sys.stderr)
        sys.exit(1)
