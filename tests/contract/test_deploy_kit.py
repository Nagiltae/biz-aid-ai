"""작은 배포 준비 테스트. 실제 AWS/Bedrock/운영 DB에는 접근하지 않는다."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("deploy_restore", ROOT / "scripts/restore_deploy_data.py")
restore = importlib.util.module_from_spec(spec)
spec.loader.exec_module(restore)
smoke_spec = importlib.util.spec_from_file_location("deploy_smoke", ROOT / "scripts/prod_smoke.py")
smoke = importlib.util.module_from_spec(smoke_spec)
smoke_spec.loader.exec_module(smoke)
rehearsal_spec = importlib.util.spec_from_file_location("deploy_rehearsal", ROOT / "scripts/rehearse_prod.py")
rehearsal = importlib.util.module_from_spec(rehearsal_spec)
rehearsal_spec.loader.exec_module(rehearsal)


class DeployKitTests(unittest.TestCase):
    def test_bundle_allowlist_and_standalone_compose(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)
            subprocess.run([str(ROOT / "scripts/make_deploy_bundle.sh"), str(path / "kit.tar.gz")], check=True, capture_output=True)
            with tarfile.open(path / "kit.tar.gz") as archive:
                names = set(archive.getnames())
                self.assertEqual(len(names), 11)
                self.assertIn("scripts/prod_smoke.py", names)
                # 2026-10-06 운영 점검(cron) 스크립트도 서버 묶음에 들어간다.
                self.assertIn("scripts/monitor_prod.sh", names)
                self.assertIn("scripts/deploy.sh", names)
                self.assertNotIn("docker-compose.build.yml", names)
                self.assertNotIn("scripts/release.sh", names)
                self.assertFalse(any(n.startswith(("backend/", "frontend/", "data-pipeline/", "harness/", "tests/")) for n in names))
                self.assertNotIn(".env.prod", names)
                archive.extractall(path, filter="data")
            environment = dict(os.environ, COMPOSE_DISABLE_ENV_FILE="1", BIZAID_IMAGE_REPO="fixture/deploy",
                BIZAID_FRONTEND_TAG="front-test", BIZAID_BACKEND_TAG="back-test", BIZAID_FASTAPI_TAG="ai-test",
                MYSQL_HOST="fixture.invalid", MYSQL_PORT="3306", MYSQL_DATABASE="fixture", MYSQL_USER="fixture", MYSQL_PASSWORD="fixture-only",
                JWT_SECRET="fixture-only", INTERNAL_AI_API_KEY="fixture-only", MYSQL_TLS_CERTS_PATH=str(path),
                BIZAID_MODEL_PATH=str(path), QDRANT_COLLECTION="bizaid_v2_fixture")
            result = subprocess.run(["docker", "compose", "--env-file", os.devnull, "-f", str(path / "docker-compose.prod.yml"),
                "config", "--format", "json"], env=environment, capture_output=True)
            self.assertEqual(result.returncode, 0)
            services = json.loads(result.stdout)["services"]
            tags = {"frontend": "front-test", "backend": "back-test", "fastapi": "ai-test"}
            # 모든 서비스에 Docker 로그 크기 제한(디스크 29GB 서버에서 로그가 디스크를 채우지 않게)이 있다.
            for name, service in services.items():
                self.assertEqual(service["logging"]["driver"], "json-file", name)
                self.assertEqual((service["logging"]["options"]["max-size"], service["logging"]["options"]["max-file"]), ("10m", "3"), name)
            for name in ["frontend", "backend", "fastapi"]:
                self.assertEqual(services[name]["image"], "fixture/deploy:" + name + "-" + tags[name])
                self.assertNotIn("build", services[name])
                self.assertEqual(services[name]["platform"], "linux/amd64")
            overridden = subprocess.run(["docker", "compose", "--env-file", os.devnull, "-f", str(path / "docker-compose.prod.yml"),
                "config", "--format", "json"], env=dict(environment, BIZAID_IMAGE_PLATFORM="linux/arm64"), capture_output=True)
            self.assertEqual(overridden.returncode, 0)
            self.assertEqual(json.loads(overridden.stdout)["services"]["fastapi"]["platform"], "linux/arm64")
            for key in ("BIZAID_FRONTEND_TAG", "BIZAID_BACKEND_TAG", "BIZAID_FASTAPI_TAG"):
                for missing in (True, False):
                    with self.subTest(key=key, absent=missing):
                        broken = dict(environment)
                        if missing: broken.pop(key)
                        else: broken[key] = ""
                        failed = subprocess.run(["docker", "compose", "--env-file", os.devnull, "-f", str(path / "docker-compose.prod.yml"),
                            "config", "--quiet"], env=broken, capture_output=True)
                        self.assertNotEqual(failed.returncode, 0)
                        self.assertIn(key, failed.stderr.decode())
            with_restore = subprocess.run(["docker", "compose", "--env-file", os.devnull, "-f", str(path / "docker-compose.prod.yml"),
                "-f", str(path / "docker-compose.restore.yml"), "config", "--format", "json"], env=environment, capture_output=True)
            self.assertEqual(with_restore.returncode, 0)
            self.assertEqual(json.loads(with_restore.stdout)["services"]["backend"]["image"], "fixture/deploy:backend-back-test")

    def test_build_only_never_pushes_and_rejects_bad_names(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            docker = directory / "docker"
            docker.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$CALLS"\n'
                'if [ "$1 $2" = "image inspect" ]; then printf "%s\\n" "${BUILT_PLATFORM:-linux/amd64}"; fi\n')
            docker.chmod(0o755)
            calls = directory / "calls"
            environment = dict(os.environ, PATH=str(directory) + os.pathsep + os.environ["PATH"], CALLS=str(calls))
            subprocess.run([str(ROOT / "scripts/push_images.sh"), "fixture/deploy", "test", "--build-only"], env=environment, capture_output=True, check=True)
            lines = calls.read_text().splitlines()
            self.assertEqual(sum("buildx build --platform linux/amd64" in line for line in lines), 3)
            self.assertFalse(any(line.startswith("push ") or line.startswith("login") for line in lines))
            subprocess.run([str(ROOT / "scripts/push_images.sh"), "fixture/deploy", "test"], env=environment, capture_output=True, check=True)
            self.assertEqual(sum(line.startswith("push fixture/deploy:") for line in calls.read_text().splitlines()), 3)
            subprocess.run([str(ROOT / "scripts/push_images.sh"), "fixture/deploy", "arm", "--platform", "linux/arm64", "--build-only"],
                env=dict(environment, BUILT_PLATFORM="linux/arm64"), capture_output=True, check=True)
            self.assertEqual(sum("buildx build --platform linux/arm64" in line for line in calls.read_text().splitlines()), 3)
            mismatch = subprocess.run([str(ROOT / "scripts/push_images.sh"), "fixture/deploy", "wrong"],
                env=dict(environment, BUILT_PLATFORM="linux/arm64"), capture_output=True)
            self.assertEqual(mismatch.returncode, 1)
            self.assertFalse(any("push fixture/deploy:frontend-wrong" in line for line in calls.read_text().splitlines()))
            bad = subprocess.run([str(ROOT / "scripts/push_images.sh"), "bad;command", "test"], env=environment, capture_output=True)
            self.assertEqual(bad.returncode, 2)
            invalid = subprocess.run([str(ROOT / "scripts/push_images.sh"), "fixture/deploy", "test", "--platform", "linux/unknown"],
                env=environment, capture_output=True)
            self.assertEqual(invalid.returncode, 2)

    def test_example_uses_placeholders_and_empty_secrets(self):
        lines = (ROOT / ".env.prod.example").read_text().splitlines()
        values = dict(line.split("=", 1) for line in lines if line and not line.startswith("#"))
        expected = {"AWS_REGION":"ap-southeast-2", "BEDROCK_REGION":"ap-northeast-2", "BIZAID_IMAGE_PLATFORM":"linux/amd64",
            "MYSQL_HOST":"YOUR_RDS_ENDPOINT", "MYSQL_DATABASE":"YOUR_DATABASE", "MYSQL_USER":"YOUR_DATABASE_USER",
            "MYSQL_SSL_MODE":"VERIFY_IDENTITY", "MYSQL_PORT":"3306", "CADDY_SITE":"example.com"}
        for name, value in expected.items():
            self.assertEqual(values[name], value, name)
        for name in ("MYSQL_PASSWORD", "MYSQL_TRUSTSTORE_PASSWORD", "JWT_SECRET", "INTERNAL_AI_API_KEY"):
            self.assertEqual(values[name], "", name)
        for name in ("BIZAID_FRONTEND_TAG", "BIZAID_BACKEND_TAG", "BIZAID_FASTAPI_TAG"):
            self.assertEqual(values[name], "", name)
        guide = (ROOT / "docs/deployment.md").read_text()
        self.assertIn("ap-southeast-2/ap-southeast-2-bundle.pem", guide)
        self.assertNotIn("AWS_S3_BUCKET", values)
        self.assertNotIn("AWS_S3_PREFIX", values)
        self.assertEqual(values["QDRANT_COLLECTION"], "bizaid_v2_YOUR_COLLECTION")
        self.assertNotRegex("\n".join(lines), r"\b\d{12}\b|\.rds\.amazonaws\.com")
        self.assertIn('deploy/${DEPLOY_TAG}', guide)
        self.assertNotIn("biz-aid/deploy/", guide)
        self.assertIn('--region $DEPLOY_REGION', guide)
        self.assertIn('--user $(id -u):$(id -g)', guide)
        for index, line in enumerate(lines):
            if line and not line.startswith("#"):
                self.assertTrue(index and lines[index - 1].startswith("#"), line.split("=", 1)[0])

    def test_existing_programs_never_write(self):
        before = "\n".join(f"{name}\t{1 if i == 0 else 0}" for i, name in enumerate(restore.TABLES)).encode()
        with patch.object(restore, "command", side_effect=[b'{"status":"ok"}', before]) as run:
            with self.assertRaisesRegex(ValueError, "overwrite_forbidden"):
                restore.restore_programs(Path("."), {"tables":dict.fromkeys(restore.TABLES, 1)})
            self.assertEqual(run.call_count, 2)

    def test_program_restore_checks_counts_before_commit(self):
        manifest = {"tables":dict.fromkeys(restore.TABLES, 1)}
        empty = "\n".join(f"{n}\t0" for n in restore.TABLES).encode()
        after = "\n".join(f"{n}\t1" for n in restore.TABLES).encode()
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)
            (source / "programs.sql").write_text("INSERT INTO support_programs VALUES(1);")
            with patch.object(restore, "command", side_effect=[b'{"status":"ok"}', empty, after]) as run:
                self.assertEqual(restore.restore_programs(source, manifest)["tables"], manifest["tables"])
                payload = run.call_args.args[2].decode()
                self.assertLess(payload.index("restore_guard VALUES"), payload.index("COMMIT"))
                self.assertIn("CHECK(ok=1)", payload)
                self.assertIn("START TRANSACTION", payload)
            (source / "programs.sql").write_text("ALTER TABLE support_programs DISABLE KEYS;")
            with patch.object(restore, "command", side_effect=[b'{"status":"ok"}', empty]) as run:
                with self.assertRaisesRegex(ValueError, "implicit_commit"):
                    restore.restore_programs(source, manifest)
                self.assertEqual(run.call_count, 2)

    def test_qdrant_refuses_existing_and_checks_exact_count(self):
        manifest = {"collection":"bizaid_v2_fixture", "point_count":2}
        with patch.object(restore, "command", return_value=b'{"result":{"collections":[{"name":"bizaid_v2_fixture"}]}}') as run:
            with self.assertRaisesRegex(ValueError, "overwrite_forbidden"):
                restore.restore_qdrant(Path("."), manifest)
            self.assertEqual(run.call_count, 1)
        with patch.object(restore, "command", side_effect=[b'{"result":{"collections":[]}}',b'{"status":"ok"}',b'{"result":{"count":2}}']):
            self.assertEqual(restore.restore_qdrant(Path("."), manifest)["point_count"], 2)
        with patch.object(restore, "command", side_effect=[b'{"result":{"collections":[]}}',b'{"status":"ok"}',b'{"result":{"count":1}}']):
            with self.assertRaisesRegex(ValueError, "count_mismatch"):
                restore.restore_qdrant(Path("."), manifest)

    def test_model_extract_checksum_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)
            name = "BAAI--bge-m3-embedding/config.json"
            content = b'{}'
            with tarfile.open(source / "models.tar.gz", "w:gz") as archive:
                item = tarfile.TarInfo(name); item.size = len(content)
                archive.addfile(item, io.BytesIO(content))
            manifest = {"model_files":{name:hashlib.sha256(content).hexdigest()}}
            target = source / "models"
            with patch.object(restore, "check_readable", return_value={"service":"fastapi", "uid":10001, "readable_files":1}):
                self.assertEqual(restore.restore_models(source, manifest, target)["verified_files"], 1)
            self.assertEqual((target / name).read_bytes(), content)
            self.assertEqual(target.stat().st_mode & 0o777, 0o755)
            self.assertEqual((target / name).stat().st_mode & 0o777, 0o644)
            with self.assertRaisesRegex(ValueError, "overwrite_forbidden"):
                restore.restore_models(source, manifest, target)
            with self.assertRaisesRegex(ValueError, "checksum_mismatch"):
                restore.restore_models(source, {"model_files":{name:"0" * 64}}, source / "bad")
            self.assertFalse((source / "bad").exists())

    def test_permission_checks_use_default_image_user_and_both_cert_services(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "rds-ca.pem").write_text("public fixture")
            (directory / "rds-ca.p12").write_bytes(b"public fixture")
            with patch.object(restore.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, b"uid=10001\nfiles=2\n", b"")) as run:
                result = restore.verify_permissions(directory, certs=True)
            self.assertEqual([row["service"] for row in result["read_checks"]], ["backend", "fastapi"])
            self.assertEqual(directory.stat().st_mode & 0o777, 0o755)
            for call in run.call_args_list:
                args = call.args[0]
                self.assertNotIn("--user", args)
                self.assertIn("--no-deps", args)
                self.assertIn("--entrypoint", args)
                self.assertEqual(call.kwargs["env"]["MYSQL_TLS_CERTS_PATH"], str(directory.resolve()))

    def test_unreadable_model_reports_path_and_retains_restored_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)
            name, content = "BAAI--bge-m3-embedding/config.json", b"{}"
            with tarfile.open(source / "models.tar.gz", "w:gz") as archive:
                item = tarfile.TarInfo(name); item.size = len(content)
                archive.addfile(item, io.BytesIO(content))
            failure = subprocess.CompletedProcess([], 1, ("unreadable_file:/models/" + name + "\n").encode(), b"hidden fixture credential")
            with patch.object(restore.subprocess, "run", return_value=failure):
                with self.assertRaisesRegex(restore.RestoreFailure, "permission_check_failed:fastapi:unreadable_file") as caught:
                    restore.restore_models(source, {"model_files":{name:hashlib.sha256(content).hexdigest()}}, source / "models")
            self.assertIn(name, str(caught.exception))
            self.assertNotIn("credential", str(caught.exception))
            self.assertEqual((source / "models" / name).read_bytes(), content)

    def test_permission_check_rejects_root_and_symlinks(self):
        with patch.object(restore.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, b"image_user_must_not_be_root\n", b"")):
            with self.assertRaisesRegex(restore.RestoreFailure, "image_user_must_not_be_root"):
                restore.check_readable("fastapi", Path("."), "/models")
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "link").symlink_to("/tmp")
            with self.assertRaisesRegex(restore.RestoreFailure, "symlink_or_special_file"):
                restore.normalize_permissions(directory)

    def test_rehearsal_images_are_explicit_and_platform_is_validated(self):
        tags = {"frontend": "front", "backend": "back", "fastapi": "ai"}
        self.assertEqual(rehearsal.image_settings("fixture/deploy", tags, "linux/amd64")["BIZAID_BACKEND_TAG"], "back")
        self.assertEqual(rehearsal.image_settings("fixture/deploy", tags, "linux/arm64")["BIZAID_IMAGE_PLATFORM"], "linux/arm64")
        for repository, chosen, platform in [(None, tags, "linux/amd64"), ("fixture/deploy", {}, "linux/amd64"),
                                             ("fixture/deploy", tags, "linux/invalid")]:
            with self.assertRaises(ValueError):
                rehearsal.image_settings(repository, chosen, platform)

    def test_smoke_failure_has_context_for_every_stage_without_tokens(self):
        replies = [b'{"status":"ok"}', b'<div id="root">', b'{"accessToken":"synthetic-known-token"}',
                   b'{"remaining":10}', b'{"result":{"requestMode":"SEARCH_LIST"}}', b'{"remaining":9}']
        stages = ["health", "landing", "trial", "usage", "ai_query", "usage"]
        paths = ["/api/health", "/", "/api/auth/trial", "/api/ai/usage", "/api/ai/query", "/api/ai/usage"]
        for failed, stage in enumerate(stages):
            position = 0
            def response(request, timeout):
                nonlocal position
                current = position
                position += 1
                if current == failed:
                    raw = b'{"accessToken":"unknown-token","detail":"Bearer synthetic-known-token","password":"fixture-secret","padding":"' + b'x' * 400 + b'"}'
                    raise HTTPError(request.full_url, 500, "fixture", {}, io.BytesIO(raw))
                output = io.BytesIO(replies[current])
                output.status = 200
                return output
            with self.subTest(stage=stage, failed=failed), patch.object(smoke, "urlopen", side_effect=response):
                with self.assertRaises(smoke.SmokeFailure) as caught:
                    smoke.smoke("https://example.com")
                details = caught.exception.details
                self.assertEqual(details["stage"], stage)
                self.assertEqual(details["url"], "https://example.com" + paths[failed])
                self.assertEqual(details["http_status"], 500)
                self.assertLessEqual(len(details["body_preview"]), 300)
                for sensitive in ("unknown-token", "synthetic-known-token", "fixture-secret"):
                    self.assertNotIn(sensitive, json.dumps(details))

    def test_smoke_validation_connection_failure_and_usage_mismatch_have_context(self):
        malformed = io.BytesIO(b'{"accessToken":"fixture-token",invalid}')
        malformed.status = 200
        with patch.object(smoke, "urlopen", return_value=malformed):
            with self.assertRaises(smoke.SmokeFailure) as caught:
                smoke.smoke("https://example.com")
            self.assertEqual(caught.exception.details["stage"], "health")
            self.assertEqual(caught.exception.details["http_status"], 200)
            self.assertNotIn("fixture-token", caught.exception.details["body_preview"])
        with patch.object(smoke, "urlopen", side_effect=URLError("hidden connection detail")):
            with self.assertRaises(smoke.SmokeFailure) as caught:
                smoke.smoke("https://example.com")
            self.assertIsNone(caught.exception.details["http_status"])
            self.assertNotIn("hidden", json.dumps(caught.exception.details))
        replies = [b'{"status":"ok"}', b'<div id="root">', b'{"accessToken":"fixture-token"}',
                   b'{"remaining":10}', b'{"result":{}}', b'{"remaining":10}']
        def responses(request, timeout):
            result = io.BytesIO(replies.pop(0))
            result.status = 200
            return result
        with patch.object(smoke, "urlopen", side_effect=responses):
            with self.assertRaises(smoke.SmokeFailure) as caught:
                smoke.smoke("https://example.com")
            self.assertEqual(caught.exception.details["stage"], "usage")
            self.assertEqual(caught.exception.details["reason"], "smoke_usage_mismatch")

    def test_smoke_scrubs_text_headers_and_success_uses_one_query(self):
        preview = smoke.body_preview('Authorization: Bearer fixture-token\nCookie: a=private; b=private2\n{"refreshToken":"other-private"}')
        for secret in ("fixture-token", "private", "other-private"):
            self.assertNotIn(secret, preview)
        replies = [b'{"status":"ok"}', b'<div id="root">', b'{"accessToken":"fixture-token"}',
                   b'{"remaining":10}', b'{"result":{"requestMode":"SEARCH_LIST"}}', b'{"remaining":9}']
        def responses(request, timeout):
            result = io.BytesIO(replies.pop(0))
            result.status = 200
            return result
        with patch.object(smoke, "urlopen", side_effect=responses) as run:
            result = smoke.smoke("https://example.com")
        self.assertEqual(result["ai_query"], "PASS")
        self.assertEqual(sum(call.args[0].full_url.endswith('/api/ai/query') for call in run.call_args_list), 1)
        self.assertNotIn("fixture-token", json.dumps(result))

    def test_client_errors_never_reflect_raw_credentials(self):
        with patch.object(restore.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, b"", b"sensitive fixture")):
            with self.assertRaisesRegex(ValueError, "raw output withheld") as caught:
                restore.command(["mysql-tools"], Path("."))
            self.assertNotIn("sensitive", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
