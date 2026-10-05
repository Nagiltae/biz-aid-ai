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

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("deploy_restore", ROOT / "scripts/restore_deploy_data.py")
restore = importlib.util.module_from_spec(spec)
spec.loader.exec_module(restore)


class DeployKitTests(unittest.TestCase):
    def test_bundle_allowlist_and_standalone_compose(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)
            subprocess.run([str(ROOT / "scripts/make_deploy_bundle.sh"), str(path / "kit.tar.gz")], check=True, capture_output=True)
            with tarfile.open(path / "kit.tar.gz") as archive:
                names = set(archive.getnames())
                self.assertEqual(len(names), 9)
                self.assertIn("scripts/prod_smoke.py", names)
                self.assertNotIn("docker-compose.build.yml", names)
                self.assertFalse(any(n.startswith(("backend/", "frontend/", "data-pipeline/", "harness/", "tests/")) for n in names))
                self.assertNotIn(".env.prod", names)
                archive.extractall(path, filter="data")
            environment = dict(os.environ, COMPOSE_DISABLE_ENV_FILE="1", BIZAID_IMAGE_REPO="fixture/deploy", BIZAID_IMAGE_TAG="test",
                MYSQL_HOST="fixture.invalid", MYSQL_PORT="3306", MYSQL_DATABASE="fixture", MYSQL_USER="fixture", MYSQL_PASSWORD="fixture-only",
                JWT_SECRET="fixture-only", INTERNAL_AI_API_KEY="fixture-only", MYSQL_TLS_CERTS_PATH=str(path),
                BIZAID_MODEL_PATH=str(path), QDRANT_COLLECTION="bizaid_v2_fixture")
            result = subprocess.run(["docker", "compose", "--env-file", os.devnull, "-f", str(path / "docker-compose.prod.yml"),
                "config", "--format", "json"], env=environment, capture_output=True)
            self.assertEqual(result.returncode, 0)
            services = json.loads(result.stdout)["services"]
            for name in ["frontend", "backend", "fastapi"]:
                self.assertEqual(services[name]["image"], "fixture/deploy:" + name + "-test")
                self.assertNotIn("build", services[name])
                self.assertEqual(services[name]["platform"], "linux/arm64")

    def test_build_only_never_pushes_and_rejects_bad_names(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            docker = directory / "docker"
            docker.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$CALLS"\n')
            docker.chmod(0o755)
            calls = directory / "calls"
            environment = dict(os.environ, PATH=str(directory) + os.pathsep + os.environ["PATH"], CALLS=str(calls))
            subprocess.run([str(ROOT / "scripts/push_images.sh"), "fixture/deploy", "test", "--build-only"], env=environment, capture_output=True, check=True)
            lines = calls.read_text().splitlines()
            self.assertEqual(sum("buildx build --platform linux/arm64" in line for line in lines), 3)
            self.assertFalse(any(line.startswith("push ") or line.startswith("login") for line in lines))
            subprocess.run([str(ROOT / "scripts/push_images.sh"), "fixture/deploy", "test"], env=environment, capture_output=True, check=True)
            self.assertEqual(sum(line.startswith("push fixture/deploy:") for line in calls.read_text().splitlines()), 3)
            bad = subprocess.run([str(ROOT / "scripts/push_images.sh"), "bad;command", "test"], env=environment, capture_output=True)
            self.assertEqual(bad.returncode, 2)

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
            self.assertEqual(restore.restore_models(source, manifest, target)["verified_files"], 1)
            self.assertEqual((target / name).read_bytes(), content)
            with self.assertRaisesRegex(ValueError, "overwrite_forbidden"):
                restore.restore_models(source, manifest, target)
            with self.assertRaisesRegex(ValueError, "checksum_mismatch"):
                restore.restore_models(source, {"model_files":{name:"0" * 64}}, source / "bad")
            self.assertFalse((source / "bad").exists())

    def test_client_errors_never_reflect_raw_credentials(self):
        with patch.object(restore.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, b"", b"sensitive fixture")):
            with self.assertRaisesRegex(ValueError, "raw output withheld") as caught:
                restore.command(["mysql-tools"], Path("."))
            self.assertNotIn("sensitive", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
