"""운영 점검 스크립트(scripts/monitor_prod.sh): 가짜 docker·aws로 판정·중복 억제·해결 메일·비밀값 비노출을 확인한다.

실제 Docker·AWS·운영 서버에 접속하지 않는다. 로그 고정 문장은 backend·FastAPI 코드의 실제 로그 형식을 따른다.
"""
import os
import re
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/monitor_prod.sh"
SECRET = "질문원문-비밀-sentinel"
# backend HttpAiGateway·GlobalExceptionHandler, FastAPI rag/llm.py의 실제 로그 형식.
BACKEND_AI = "2026-10-06T01:00:00.000Z  WARN 1 --- [bizaid-backend] [nio-8080-exec-1] c.b.ai.infrastructure.HttpAiGateway      : AI upstream error path=/internal/v1/query status=503"
BACKEND_TIMEOUT = "2026-10-06T01:00:01.000Z  WARN 1 --- [bizaid-backend] [nio-8080-exec-2] c.b.ai.infrastructure.HttpAiGateway      : AI upstream io failure path=/internal/v2/workflows/start type=HttpTimeoutException"
BACKEND_ERROR = "2026-10-06T01:00:02.000Z ERROR 1 --- [bizaid-backend] [nio-8080-exec-3] c.b.common.error.GlobalExceptionHandler  : unexpected error"
FASTAPI_BEDROCK = "Bedrock invocation failed (ReadTimeoutError)"

FAKE_DOCKER = r"""#!/usr/bin/env bash
# 테스트용 가짜 docker: ps는 running 서비스의 ID, exec는 FastAPI 상태, logs는 고정 로그를 돌려준다.
case "$1" in
  ps)
    for arg in "$@"; do case "$arg" in label=com.docker.compose.service=*) service="${arg#*=}"; service="${service#*=}";; esac; done
    grep -qx "$service" "$FAKE/running" && echo "id-$service"; exit 0 ;;
  exec) exit "$(cat "$FAKE/health")" ;;
  logs) cat "$FAKE/logs-${@: -1}" 2>/dev/null; exit 0 ;;
esac
exit 0
"""
FAKE_AWS = r"""#!/usr/bin/env bash
# 테스트용 가짜 aws: 받은 인자를 기록하고 정해진 종료 코드를 돌려준다.
printf '%s\n' "$@" >> "$FAKE/aws-calls"; echo "----" >> "$FAKE/aws-calls"
exit "$(cat "$FAKE/aws-exit")"
"""


class MonitorProdTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.dir = Path(self.temporary.name)
        (self.dir / "bin").mkdir()
        for name, body in (("docker", FAKE_DOCKER), ("aws", FAKE_AWS)):
            path = self.dir / "bin" / name
            path.write_text(body, encoding="utf-8")
            path.chmod(path.stat().st_mode | stat.S_IEXEC)
        (self.dir / "running").write_text("caddy\nfrontend\nbackend\nfastapi\nqdrant\n", encoding="utf-8")
        (self.dir / "health").write_text("0", encoding="utf-8")
        (self.dir / "aws-exit").write_text("0", encoding="utf-8")
        (self.dir / "meminfo").write_text("MemTotal: 8000000 kB\nMemAvailable: 4000000 kB\n", encoding="utf-8")
        (self.dir / "monitor.conf").write_text(
            "# 테스트 설정\nSNS_TOPIC_ARN=arn:aws:sns:ap-southeast-2:000000000000:bizaid-alerts\nDISK_PERCENT=101\n", encoding="utf-8")
        self.logs("", "")

    def tearDown(self):
        self.temporary.cleanup()

    def logs(self, backend, fastapi):
        (self.dir / "logs-id-backend").write_text(backend, encoding="utf-8")
        (self.dir / "logs-id-fastapi").write_text(fastapi, encoding="utf-8")

    def run_monitor(self, *args):
        environment = dict(os.environ, PATH=str(self.dir / "bin") + ":" + os.environ["PATH"], FAKE=str(self.dir),
                           BIZAID_MONITOR_CONF=str(self.dir / "monitor.conf"), BIZAID_MONITOR_STATE=str(self.dir / "state"),
                           BIZAID_MONITOR_MEMINFO=str(self.dir / "meminfo"))
        return subprocess.run(["bash", str(SCRIPT), *args], env=environment, capture_output=True, text=True, timeout=60)

    def mails(self):
        path = self.dir / "aws-calls"
        return [call for call in path.read_text(encoding="utf-8").split("----\n") if call.strip()] if path.exists() else []

    def test_alert_once_per_hour_then_resolved_and_no_log_content_leaks(self):
        # backend AI 오류 2 + 시간 초과 1 = 3(기준), FastAPI 1 → 큰 값 3. ERROR 10줄 + stack trace 줄(세지 않음).
        backend = "\n".join([BACKEND_AI + " " + SECRET, BACKEND_AI, BACKEND_TIMEOUT] + [BACKEND_ERROR + " " + SECRET] * 10
                            + ["\tat com.bizaid.Example(Example.java:1)", "ERROR 문장으로 시작하지 않는 줄"]) + "\n"
        self.logs(backend, FASTAPI_BEDROCK + "\n")
        first = self.run_monitor()
        self.assertEqual(first.returncode, 0, first.stderr)
        mails = self.mails()
        self.assertEqual(len(mails), 1)
        self.assertIn("[BizAid] ALERT 2 issue(s)", mails[0])
        self.assertIn("AI(Bedrock) 호출 실패·시간 초과 3건", mails[0])
        self.assertIn("backend ERROR 로그 10건", mails[0])
        # RISK: 로그 내용(질문·경로)은 메일·화면에 나오지 않는다.
        for text in (mails[0], first.stdout, first.stderr):
            self.assertNotIn(SECRET, text)
            self.assertNotIn("/internal/v1/query", text)
        self.assertEqual(sorted(path.name for path in (self.dir / "state").glob("*.sent")), ["ai_failures.sent", "backend_errors.sent"])
        # 1시간 안의 같은 문제는 다시 보내지 않는다.
        self.assertEqual(self.run_monitor().returncode, 0)
        self.assertEqual(len(self.mails()), 1)
        # 문제가 풀리면 해결 메일 1통, 상태 파일 정리.
        self.logs("", "")
        self.assertEqual(self.run_monitor().returncode, 0)
        mails = self.mails()
        self.assertEqual(len(mails), 2)
        self.assertIn("[BizAid] RESOLVED 2 issue(s)", mails[1])
        self.assertEqual(list((self.dir / "state").glob("*.sent")), [])
        self.assertEqual(self.run_monitor().returncode, 0)
        self.assertEqual(len(self.mails()), 2)

    def test_container_health_memory_disk_and_thresholds(self):
        (self.dir / "running").write_text("caddy\nfrontend\nbackend\nfastapi\n", encoding="utf-8")
        (self.dir / "health").write_text("1", encoding="utf-8")
        (self.dir / "meminfo").write_text("MemTotal: 8000000 kB\nMemAvailable: 400000 kB\n", encoding="utf-8")
        (self.dir / "monitor.conf").write_text("SNS_TOPIC_ARN=arn:aws:sns:ap-southeast-2:000000000000:bizaid-alerts\nDISK_PERCENT=0\n",
                                               encoding="utf-8")
        # 기준 미만(AI 2건·ERROR 9건)은 문제가 아니다.
        self.logs("\n".join([BACKEND_AI] * 2 + [BACKEND_ERROR] * 9) + "\n", "")
        self.assertEqual(self.run_monitor().returncode, 0)
        mail = self.mails()[0]
        for text in ("컨테이너 qdrant 가 실행 중이 아닙니다", "FastAPI가 내부 상태 확인(/health)에 응답하지 않습니다",
                     "메모리 사용률 95%", "디스크 사용률"):
            self.assertIn(text, mail)
        self.assertNotIn("AI(Bedrock)", mail)
        self.assertNotIn("backend ERROR", mail)

    def test_dry_run_test_mail_and_send_failure(self):
        self.logs("\n".join([BACKEND_ERROR] * 10) + "\n", "")
        dry = self.run_monitor("--dry-run")
        self.assertEqual(dry.returncode, 0)
        self.assertIn("[dry-run] 보낼 메일", dry.stdout)
        self.assertEqual((self.mails(), (self.dir / "state").exists()), ([], False))
        test = self.run_monitor("--test")
        self.assertEqual(test.returncode, 0)
        self.assertIn("TEST monitor mail", self.mails()[0])
        # 전송 실패: 실패 종료하고 상태를 남기지 않아 다음 실행에서 다시 보낸다. aws 오류 원문은 출력하지 않는다.
        (self.dir / "aws-exit").write_text("1", encoding="utf-8")
        failed = self.run_monitor()
        self.assertEqual(failed.returncode, 1)
        self.assertIn("SNS 메일 전송 실패", failed.stderr)
        self.assertEqual(list((self.dir / "state").glob("*.sent")), [])
        # 주제 ARN이 없으면 보내지 않고 실패한다.
        (self.dir / "monitor.conf").write_text("DISK_PERCENT=101\n", encoding="utf-8")
        missing = self.run_monitor()
        self.assertEqual(missing.returncode, 1)
        self.assertIn("SNS_TOPIC_ARN이 없습니다", missing.stderr)
        self.assertEqual(self.run_monitor("--bad").returncode, 2)

    def test_script_boundaries(self):
        source = SCRIPT.read_text(encoding="utf-8")
        # 주석(설명)을 뺀 실행 줄만 본다. 주제 ARN·계정 번호를 코드에 넣지 않고, .env.prod·DB를 읽지 않으며, 설정 파일을 셸로 실행하지 않는다.
        code = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#"))
        self.assertIsNone(re.search(r"arn:aws:sns:[a-z0-9-]+:[0-9]{12}", source))
        for forbidden in (".env.prod", "--env-file", "mysql", "source \"$CONF\"", ". \"$CONF\""):
            self.assertNotIn(forbidden, code)
        self.assertIn('--filter "label=com.docker.compose.project=$COMPOSE_PROJECT"', source)
        self.assertTrue(os.access(SCRIPT, os.X_OK))
        bundle = (ROOT / "scripts/make_deploy_bundle.sh").read_text(encoding="utf-8")
        self.assertIn("scripts/monitor_prod.sh", bundle)


if __name__ == "__main__":
    unittest.main()
