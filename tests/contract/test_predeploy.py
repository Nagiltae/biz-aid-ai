"""배포 경계는 합성 설정과 가짜 서비스로 검사한다. AWS·사용자 Secret 파일을 읽지 않는다."""
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data-pipeline/src"))
from biz_aid_pipeline.config.settings import DbConfig, PipelineError, S3Config, profile_values
from biz_aid_pipeline.observability.tracing import TraceSettings
from biz_aid_pipeline.runtime import ServiceRuntime


class ProductionBoundaryTests(unittest.TestCase):
    def config(self):
        return {"BIZAID_ENV": "prod", "MYSQL_HOST": "rds.example.invalid", "MYSQL_PORT": "3306",
                "MYSQL_DATABASE": "fixture", "MYSQL_USER": "fixture", "MYSQL_PASSWORD": "fixture-only",
                "MYSQL_SSL_MODE": "REQUIRED", "QDRANT_URL": "http://qdrant:6333", "QDRANT_COLLECTION": "fixed_v2"}

    def test_production_process_only_explicit_remote_and_tls(self):
        environment = self.config()
        with patch.object(Path, "read_text", side_effect=AssertionError("secret file read")):
            config = DbConfig.load_service(ROOT, "prod", environment)
            self.assertEqual(config.host, "rds.example.invalid")
            self.assertIn("ssl", config.connect_args())
            self.assertNotIn("fixture-only", repr(config))
            self.assertEqual(profile_values(ROOT, "prod", {"MYSQL_HOST"}, environment), {"MYSQL_HOST": config.host})
        with self.assertRaisesRegex(PipelineError, "prod_database_access_forbidden"):
            DbConfig.load(ROOT, "prod", environment)
        # BOUNDARY: 운영 DB 예외가 수집·S3 저장 설정으로 확산되지 않도록 기존 저장 경계를 확인한다.
        self.assertFalse(hasattr(S3Config, "load_service"))
        with self.assertRaisesRegex(PipelineError, "prod_s3_access_forbidden"):
            S3Config.load(ROOT, "prod", environment)
        for missing in ("BIZAID_ENV", "MYSQL_HOST", "MYSQL_PASSWORD"):
            values = dict(environment)
            del values[missing]
            with self.assertRaises(PipelineError):
                DbConfig.load_service(ROOT, "prod", values)
        environment["MYSQL_SSL_MODE"] = "VERIFY_IDENTITY"
        with self.assertRaisesRegex(PipelineError, "mysql_tls_ca_required"):
            DbConfig.load_service(ROOT, "prod", environment)

    def test_production_tracing_cannot_be_enabled(self):
        with patch.object(Path, "read_text", side_effect=AssertionError("secret file read")):
            settings = TraceSettings.load(ROOT, "prod", {"BIZAID_TRACING_ENABLED": "true", "LANGSMITH_API_KEY": "fixture"})
            self.assertFalse(settings.enabled)
            self.assertEqual(settings.api_key, "")

    def test_fixed_collection_readiness_failure_and_no_creation(self):
        for exists, count, expected in ((True, 12, True), (False, 0, False), (True, 0, False)):
            client, repo = Mock(), Mock()
            client.collection_exists.return_value = exists
            client.count.return_value = SimpleNamespace(count=count)
            with patch.dict(os.environ, self.config(), clear=True), patch("qdrant_client.QdrantClient", return_value=client), \
                    patch("biz_aid_pipeline.candidates.service.ProgramCandidateRepository.from_config", return_value=repo), \
                    patch("biz_aid_pipeline.rag.llm.provider_from_settings", return_value=Mock()):
                if expected:
                    runtime = ServiceRuntime("prod")
                    self.assertEqual(runtime.fixed_collection, "fixed_v2")
                    runtime.close()
                else:
                    with self.assertRaisesRegex(PipelineError, "production_collection_not_ready"):
                        ServiceRuntime("prod")
                    repo.close.assert_called_once()
                client.create_collection.assert_not_called()
                client.upsert.assert_not_called()

    def test_production_docs_hidden_health_safe_and_errors_redacted(self):
        from fastapi.testclient import TestClient
        from biz_aid_pipeline.api.app import create_app
        runtime = Mock()
        runtime.answer_query.side_effect = PipelineError("llm_provider_unavailable:private_detail")
        with patch.dict(os.environ, {"BIZAID_ENV": "prod", "LANGSMITH_TRACING": "true"}):
            with TestClient(create_app(lambda: runtime, api_key="fixture-key")) as client:
                self.assertEqual(client.get("/health").json(), {"status": "ok"})
                for path in ("/docs", "/redoc", "/openapi.json"):
                    self.assertEqual(client.get(path).status_code, 404)
                response = client.post("/internal/v1/query", json={"query": "시험"}, headers={"X-Internal-Api-Key": "fixture-key"})
                self.assertEqual(response.status_code, 503)
                self.assertNotIn("private_detail", response.text)
                invalid = client.post("/internal/v1/eligibility", json={"pblanc_id": "PBLN_000000000000001", "company_profile": {"credit_score": "high"}},
                                      headers={"X-Internal-Api-Key": "fixture-key"})
                self.assertEqual((invalid.status_code, invalid.json()["error"]["code"]), (422, "company_profile_invalid"))
            self.assertEqual(os.environ["LANGSMITH_TRACING"], "false")

    def test_production_assets_and_no_credential_mount(self):
        compose = (ROOT / "docker-compose.prod.yml").read_text()
        self.assertNotIn(".aws", compose)
        self.assertNotIn("AWS_ACCESS_KEY", compose)
        self.assertNotIn("--reload", compose)
        self.assertNotIn("  mysql:", compose)
        self.assertIn("BIZAID_ENV: prod", compose)
        self.assertIn("BIZAID_TRIAL_ENABLED:-true", compose)
        self.assertIn("max-size: 10m", compose)
        caddy = (ROOT / "Caddyfile").read_text()
        self.assertIn("header_up X-Forwarded-For {remote_host}", caddy)
        nginx = (ROOT / "frontend/nginx.prod.conf").read_text()
        self.assertIn("proxy_set_header X-Forwarded-For $remote_addr", nginx)
        self.assertNotIn("$proxy_add_x_forwarded_for", nginx)
        self.assertIn("set_real_ip_from 172.29.52.0/24", nginx)
        for line in (ROOT / ".env.prod.example").read_text().splitlines():
            if line and not line.startswith("#"):
                self.assertTrue(line.endswith("="), line)


class SmokePortabilityTests(unittest.TestCase):
    def test_stdlib_smoke_and_sensitive_response_not_logged(self):
        import importlib.util
        import io
        spec = importlib.util.spec_from_file_location("prod_smoke", ROOT / "scripts/prod_smoke.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        bodies = [b'{"status":"ok"}', b'<div id="root"></div>', b'{"accessToken":"fixture-token"}',
                  b'{"remaining":10}', b'{"result":{"requestMode":"SEARCH_LIST","status":"LISTED"}}', b'{"remaining":9}']
        def respond(request, **kwargs):
            return io.BytesIO(bodies.pop(0))
        with patch.object(module, "urlopen", side_effect=respond):
            result = module.smoke("https://fixture.invalid")
        self.assertEqual(result["remaining"], 9)
        self.assertNotIn("fixture-token", str(result))
