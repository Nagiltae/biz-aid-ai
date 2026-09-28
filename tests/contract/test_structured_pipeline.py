import copy
import hashlib
import json
import os
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data-pipeline/src"))
from biz_aid_pipeline.bizinfo.client import BizinfoClient
from biz_aid_pipeline.bizinfo.models import SourceAnnouncement, SourceBatch, SourcePage, SyncScope
from biz_aid_pipeline.config.settings import ApiConfig, DbConfig, PipelineError, api_contract, values
from biz_aid_pipeline.config.settings import profile_values
from biz_aid_pipeline.ingestion.normalizer import FIELD_MAPPING, normalize, period, url_valid
from biz_aid_pipeline.ingestion.sample import SAMPLE_RUN, load_pilot_sample
from biz_aid_pipeline.quality.structured_data_gate import quality_report, reconciliation_reasons, validate_report


def source(identifier="PBLN_TEST_1", **values):
    return dict(pblancId=identifier, pblancNm="합성 공고", reqstBeginEndDe="2026-09-01 ~ 2026-09-30", **values)


def batch(items=None, scope=SyncScope.SAMPLE, **values):
    items = [source()] if items is None else items
    return SourceBatch(scope, (SourcePage(1, max(1, len(items)), tuple(items), len(items)),), "synthetic", True, **values)


class StructuredModelTests(unittest.TestCase):
    def test_known_fields_match_existing_contract(self):
        self.assertEqual(set(SourceAnnouncement.model_fields), set(api_contract(ROOT)["response"]["item_fields"]))
        self.assertEqual(set(FIELD_MAPPING) | {"pblancId"}, set(SourceAnnouncement.model_fields))

    def test_source_roundtrip_real_user_sanitized_fixture(self):
        payload = json.loads((ROOT / "tests/fixtures/external-api/bizinfo-user-sample.json").read_bytes())
        for item in payload["response"]["body"]["items"]["item"]:
            self.assertEqual(normalize(item).source_payload, item)

    def test_required_identifier(self):
        for value in (None, "", " ", 10, True, "wrong/id", " x ", "가나다"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize({"pblancId": value})
        with self.assertRaises(ValueError):
            normalize({})

    def test_strict_fields(self):
        for field, value in (("pblancNm", 2), ("inqireCo", "2"), ("inqireCo", True)):
            with self.assertRaises(ValueError):
                normalize(dict(source(), **{field: value}))

    def test_unknown_fields_preserved(self):
        raw = dict(source(), future={"b": None, "a": [1, ""]})
        self.assertEqual(normalize(raw).source_payload, raw)

    def test_null_empty_missing_distinct(self):
        raws = [dict(source(), fileNm=None), dict(source(), fileNm=""), source()]
        fingerprints = {normalize(s).source_fingerprint for s in raws}
        self.assertEqual(len(fingerprints), 3)
        for raw in raws:
            self.assertEqual(normalize(raw).source_payload, raw)

    def test_raw_values_not_trimmed_or_html_removed(self):
        raw = dict(source(), bsnsSumryCn=" <p>원문</p> ", fileNm=" a.hwp@b.pdf ")
        item = normalize(raw)
        self.assertEqual(item.content["summary_html"], raw["bsnsSumryCn"])
        self.assertEqual(item.content["attachment_names_raw"], raw["fileNm"])

    def test_date_range(self):
        item = normalize(source())
        self.assertEqual(str(item.content["application_start_date"]), "2026-09-01")
        self.assertEqual(str(item.content["application_end_date"]), "2026-09-30")

    def test_free_text_is_normal(self):
        raw = dict(source(), reqstBeginEndDe=" 예산 소진시까지 ")
        item = normalize(raw)
        self.assertEqual(item.period_class, "FREE_TEXT")
        self.assertIsNone(item.content["application_start_date"])
        self.assertEqual(item.content["application_period_raw"], raw["reqstBeginEndDe"])

    def test_invalid_date_and_reverse_range_preserved(self):
        for raw in ("2026-02-30 ~ 2026-03-01", "2026-10-01 ~ 2026-09-01"):
            self.assertEqual(period(raw)[2], "INVALID_DATE_RANGE")

    def test_missing_date(self):
        for raw in (None, "", " "):
            self.assertEqual(period(raw), (None, None, "UNAVAILABLE"))

    def test_timestamp_without_timezone_guess(self):
        item = normalize(source(creatPnttm="2026-09-23 13:50:28", updtPnttm="not-time"))
        self.assertIsNone(item.content["source_created_at"].tzinfo)
        self.assertIsNone(item.content["source_updated_at"])
        self.assertEqual(item.content["source_updated_raw"], "not-time")

    def test_fingerprint_canonical(self):
        raw = dict(source(), future={"z": 2, "a": 1})
        reordered = dict(reversed(list(raw.items())))
        reordered["future"] = {"a": 1, "z": 2}
        self.assertEqual(normalize(raw).source_fingerprint, normalize(reordered).source_fingerprint)

    def test_fingerprint_change(self):
        raw = source()
        changed = dict(raw, pblancNm="변경")
        self.assertNotEqual(normalize(raw).source_fingerprint, normalize(changed).source_fingerprint)

    def test_normalizer_not_mutating_input(self):
        raw = dict(source(), future={"x": [1]})
        original = copy.deepcopy(raw)
        normalize(raw)
        self.assertEqual(raw, original)

    def test_nonfinite_unknown_rejected(self):
        with self.assertRaises(ValueError):
            normalize(source(future=float("nan")))

    def test_invalid_url_observation(self):
        self.assertEqual(normalize(source(printFlpthNm="not a url")).invalid_urls, 1)
        self.assertFalse(url_valid("https://user:pass@example.org/x"))
        self.assertTrue(url_valid("https://www.bizinfo.go.kr/x?a=1"))


class CompletenessTests(unittest.TestCase):
    def proof(self, data):
        report = quality_report(data, "synthetic-full")
        report["status"] = "PASS"
        return report

    def test_full_success(self):
        data = batch(scope=SyncScope.FULL)
        self.assertEqual(reconciliation_reasons(data, self.proof(data)), [])

    def test_sample_partial_no_absence(self):
        for scope in (SyncScope.SAMPLE, SyncScope.PARTIAL):
            data = batch(scope=scope)
            self.assertIn("scope_is_not_FULL", reconciliation_reasons(data, self.proof(data)))

    def test_each_fatal_error_disallows_full(self):
        data = batch(scope=SyncScope.FULL)
        for name in ("transport_errors", "api_errors", "contract_errors", "normalization_fatal_errors", "persistence_fatal_errors", "duplicate_count"):
            with self.subTest(name=name):
                report = self.proof(data)
                report[name] = 1
                self.assertIn(name, reconciliation_reasons(data, report))

    def test_total_count_mismatch(self):
        data = batch(scope=SyncScope.FULL)
        data = replace(data, pages=(replace(data.pages[0], total_count=2),))
        self.assertIn("unique_count_totalCount_mismatch", reconciliation_reasons(data, self.proof(data)))

    def test_total_count_inconsistent(self):
        data = SourceBatch(SyncScope.FULL, (SourcePage(1, 1, (source(),), 2),
            SourcePage(2, 1, (source("PBLN_TEST_2"),), 3)), "synthetic", True)
        self.assertIn("totalCount_not_consistent", reconciliation_reasons(data, self.proof(data)))

    def test_normal_termination_required(self):
        data = replace(batch(scope=SyncScope.FULL), pagination_terminated=False)
        self.assertIn("pagination_not_normally_terminated", reconciliation_reasons(data, self.proof(data)))

    def test_duplicate_detected(self):
        data = batch([source(), source()], SyncScope.FULL)
        self.assertIn("duplicate_count", reconciliation_reasons(data, self.proof(data)))

    def test_missing_page(self):
        data = replace(batch(scope=SyncScope.FULL), pages=(SourcePage(2, 1, (source(),), 1),))
        self.assertIn("page_sequence_incomplete", reconciliation_reasons(data, self.proof(data)))

    def test_empty_universe_not_automatic_delete(self):
        data = batch([], SyncScope.FULL)
        self.assertIn("empty_universe_unconfirmed", reconciliation_reasons(data, self.proof(data)))

    def test_run_failure(self):
        data = batch(scope=SyncScope.FULL)
        report = self.proof(data)
        report["status"] = "FAIL"
        self.assertIn("run_not_SUCCESS", reconciliation_reasons(data, report))

    def test_success_outcome_cannot_hide_bad_page_contract(self):
        data = batch(scope=SyncScope.SAMPLE)
        for changes in ({"http_status": 500}, {"echo_matches": False}, {"result_code": "03"}, {"total_count": True}):
            with self.subTest(changes=changes):
                changed = replace(data, pages=(replace(data.pages[0], **changes),))
                self.assertEqual(quality_report(changed, "unit")["contract_errors"], 1)


class ClientConfigTests(unittest.TestCase):
    def response(self, code="00", message="NORMAL_SERVICE", items=None, total=1):
        return json.dumps({"response": {"header": {"resultCode": code, "resultMsg": message},
            "body": {"items": {"item": [source()] if items is None else items} if code == "00" else {},
                "pageNo": 1, "numOfRows": 1 if code == "00" else 0, "totalCount": total}}}).encode()

    def client(self, raw):
        config = ApiConfig("dev", api_contract(ROOT)["request"]["endpoint"], "synthetic-secret-1234")
        return BizinfoClient(config, ROOT, lambda url: (200, raw))

    def test_success(self):
        self.assertEqual(self.client(self.response()).fetch_page(1, 1).outcome, "SUCCESS")

    def test_negative_only_explicit(self):
        raw = self.response("03", "NODATA_ERROR", total=0)
        for identifier, negative, expected in ((None, False, "API_ERROR"), ("known", False, "API_ERROR"), ("missing", True, "EXPECTED_NO_DATA")):
            result = self.client(raw).fetch_page(1, 1, identifier, negative)
            self.assertEqual(result.outcome, expected)

    def test_bad_envelope(self):
        self.assertEqual(self.client(b"{}").fetch_page(1).outcome, "CONTRACT_ERROR")

    def test_secret_reflection(self):
        result = self.client(b"synthetic-secret-1234").fetch_page(1)
        self.assertEqual(result.outcome, "CONTRACT_ERROR")
        self.assertNotIn("synthetic-secret", repr(result))

    def test_transport_exception_secret_not_reported(self):
        from urllib.error import URLError
        client = self.client(b"{}")
        def transport(url):
            raise URLError(url)
        client.transport = transport
        result = client.fetch_page(1)
        self.assertEqual(result.outcome, "TRANSPORT_ERROR")
        self.assertNotIn("synthetic-secret", repr(result))

    def test_prod_no_api_transport(self):
        with self.assertRaises(PipelineError):
            BizinfoClient(ApiConfig("prod", "https://example.org", "x"), ROOT)

    def test_prod_no_db_secret_read(self):
        with patch.object(Path, "read_text", side_effect=AssertionError("must not read")):
            with self.assertRaises(PipelineError):
                DbConfig.load(ROOT, "prod")

    def test_profile_no_fallback_and_os_precedence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / ".env.dev").write_text("BIZINFO_SERVICE_KEY=file-key\n")
            (root / ".env.prod").write_text("BIZINFO_SERVICE_KEY=prod-file-key\n")
            with patch("biz_aid_pipeline.config.settings.api_contract", return_value=api_contract(ROOT)):
                self.assertEqual(ApiConfig.load(root, "dev", {}).key, "file-key")
                self.assertEqual(ApiConfig.load(root, "prod", {}).key, "prod-file-key")
                self.assertEqual(ApiConfig.load(root, "dev", {"BIZINFO_SERVICE_KEY": "os-key"}).key, "os-key")
                (root / ".env.dev").unlink()
                self.assertEqual(ApiConfig.load(root, "dev", {}).key, "")
                (root / ".env.dev").write_text("BIZINFO_SERVICE_KEY=file-key\n")
                (root / ".env.prod").unlink()
                self.assertEqual(ApiConfig.load(root, "prod", {}).key, "")

    def test_no_shell_evaluation(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / ".env.dev"
            marker = Path(temp) / "executed"
            value = f"$(touch {marker})"
            path.write_text(f"KEY={value}\n")
            self.assertEqual(values(path, {"KEY"}, {})["KEY"], value)
            self.assertFalse(marker.exists())

    def test_full_scan_stops_and_no_retry(self):
        client = self.client(self.response())
        result = client.scan_full(rows=1, max_pages=2)
        self.assertTrue(result.pagination_terminated)
        self.assertEqual(len(result.pages), 1)

    def test_full_failure_not_complete(self):
        client = self.client(b"{}")
        result = client.scan_full(rows=1)
        self.assertFalse(result.pagination_terminated)
        self.assertEqual(len(result.pages), 1)

    def test_arbitrary_endpoint_rejected(self):
        with self.assertRaises(PipelineError):
            BizinfoClient(ApiConfig("dev", "https://example.org", "secret"), ROOT)

    def test_strict_duplicate_json_rejected(self):
        self.assertEqual(self.client(b'{"response": {}, "response": {}}').fetch_page(1).outcome, "CONTRACT_ERROR")

    def test_positive_echo_mismatch(self):
        payload = json.loads(self.response())
        payload["response"]["body"]["pageNo"] = 2
        self.assertEqual(self.client(json.dumps(payload).encode()).fetch_page(1, 1).outcome, "CONTRACT_ERROR")

    def test_unknown_profile(self):
        for profile in ("local", "staging", "test"):
            with self.assertRaises(PipelineError):
                ApiConfig.load(ROOT, profile)

    def test_api_secret_repr_hidden(self):
        config = ApiConfig("dev", api_contract(ROOT)["request"]["endpoint"], "synthetic-secret")
        self.assertNotIn("synthetic-secret", repr(config))
        db = DbConfig("127.0.0.1", 3306, "biz_aid_dev", "biz_aid", "synthetic-secret")
        self.assertNotIn("synthetic-secret", repr(db))

    def test_db_os_precedence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / ".env.dev").write_text("MYSQL_DATABASE=biz_aid_dev\nMYSQL_USER=biz_aid\nMYSQL_PASSWORD=file-secret\n")
            config = DbConfig.load(root, "dev", {"MYSQL_PASSWORD": "os-secret"})
            self.assertEqual(config.password, "os-secret")


class StructuredOutputRoutingTests(unittest.TestCase):
    def test_codex_cli_creates_task_artifact_and_report_without_live_access(self):
        import contextlib
        import io
        from types import SimpleNamespace
        from biz_aid_pipeline import cli
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            report = quality_report(batch(), "synthetic-routing")
            report.update(status="PASS", inserted=1, finished_at=report["started_at"],
                reconciliation_skipped_reason=["scope_is_not_FULL"])
            repository = Mock()
            destination = "harness/workspace/reports/codex/synthetic.md"
            with patch.object(cli, "ROOT", root), patch.object(cli, "load_pilot_sample", return_value=batch()), \
                    patch.object(cli.DbConfig, "load", return_value=SimpleNamespace(password="synthetic-password")), \
                    patch.object(cli.ApiConfig, "load", return_value=SimpleNamespace(key="synthetic-key")), \
                    patch.object(cli, "MysqlRepository", return_value=repository), patch.object(cli, "ingest", return_value=report), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(["--profile", "dev", "--run-id", "synthetic-routing", "--report", destination]), 0)
            self.assertTrue((root / destination).is_file())
            artifact = root / "harness/workspace/artifacts/codex/phase1a-structured-pipeline/structured-synthetic-routing.json"
            self.assertEqual(json.loads(artifact.read_text()), report)
            self.assertFalse((root / "harness/workspace/artifacts/structured-synthetic-routing.json").exists())
            repository.close.assert_called_once()

    def test_codex_cli_rejects_agy_and_legacy_root_before_db_or_api(self):
        import contextlib
        import io
        from biz_aid_pipeline import cli
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            for destination in ("harness/workspace/reports/agy/review.md", "harness/workspace/reports/old.md"):
                with patch.object(cli, "ROOT", root), patch.object(cli, "load_pilot_sample") as sample, \
                        patch.object(cli, "MysqlRepository") as repository, contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(cli.main(["--profile", "dev", "--run-id", "synthetic-routing", "--report", destination]), 1)
                sample.assert_not_called()
                repository.assert_not_called()
                self.assertFalse((root / destination).exists())


class StructuredQualityContractTests(unittest.TestCase):
    def report(self):
        value = quality_report(batch(), "unit-quality")
        value.update(status="PASS", inserted=1, finished_at=value["started_at"],
            reconciliation_skipped_reason=["scope_is_not_FULL"])
        return value

    def test_valid_report(self):
        self.assertEqual(validate_report(self.report())["status"], "PASS")

    def test_bad_counter_type(self):
        for value in (True, -1, "1"):
            report = self.report()
            report["inserted"] = value
            with self.assertRaises(PipelineError):
                validate_report(report)

    def test_missing_field(self):
        report = self.report()
        report.pop("reactivated")
        with self.assertRaises(KeyError):
            validate_report(report)

    def test_false_pass_rejected(self):
        report = self.report()
        report["updated"] = 1
        with self.assertRaises(PipelineError):
            validate_report(report)

    def test_sample_delete_rejected(self):
        report = self.report()
        report.update(reconciliation_attempted=True, reconciliation_executed=True, soft_deleted=1,
            reconciliation_skipped_reason=[])
        with self.assertRaises(PipelineError):
            validate_report(report)

    def test_reactivated_counter_is_subset(self):
        report = self.report()
        report["reactivated"] = 1
        with self.assertRaises(PipelineError):
            validate_report(report)

    def test_unexecuted_delete_rejected(self):
        report = self.report()
        report["soft_deleted"] = 1
        with self.assertRaises(PipelineError):
            validate_report(report)

    def test_fingerprint_lifecycle_not_included(self):
        normalized = normalize(source())
        forbidden = {"created_at", "updated_at", "last_seen_at", "run_id", "source_active", "source_deleted", "source_deleted_at"}
        self.assertFalse(forbidden & normalized.source_payload.keys())
        self.assertFalse(forbidden & normalized.content.keys())

    def test_sql_contains_no_physical_delete(self):
        import inspect
        from biz_aid_pipeline.persistence.mysql_repository import MysqlRepository
        self.assertNotIn("delete(", inspect.getsource(MysqlRepository))

    def test_sample_contract_fixed_5x20(self):
        spec = json.loads((ROOT / "contracts/schemas/structured-data-quality.contract.json").read_bytes())
        self.assertEqual(spec["pilot"]["source_run_id"], "api-quality-dev-20260928-01")
        self.assertEqual((spec["pilot"]["pages"], spec["pilot"]["rows_per_page"], spec["pilot"]["target"]), (5, 20, 100))
        self.assertFalse(spec["pilot"]["live_full_execution"])


class PilotEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        contract_dir = self.root / "contracts/external-api"
        contract_dir.mkdir(parents=True)
        (contract_dir / "bizinfo.contract.json").write_bytes((ROOT / "contracts/external-api/bizinfo.contract.json").read_bytes())
        entries = []
        for number in range(1, 6):
            directory = self.root / f"data/raw/{SAMPLE_RUN}-page{number}"
            directory.mkdir(parents=True)
            items = [source(f"SYNTHETIC_{number}_{index}") for index in range(20)]
            payload = {"response": {"header": {"resultCode": "00", "resultMsg": "NORMAL_SERVICE"},
                "body": {"items": {"item": items}, "numOfRows": 20, "pageNo": number, "totalCount": 1514}}}
            raw = json.dumps(payload).encode()
            digest = hashlib.sha256(raw).hexdigest()
            (directory / "response.json").write_bytes(raw)
            metadata = {"run_id": f"{SAMPLE_RUN}-page{number}", "raw_path": "response.json", "sha256": digest, "byte_count": len(raw)}
            (directory / "metadata.json").write_text(json.dumps(metadata))
            entries.append({"raw_snapshot": f"data/raw/{SAMPLE_RUN}-page{number}/metadata.json", "outcome": "SUCCESS", "sha256": digest, "totalCount": 1514})
        self.run = {"run_id": SAMPLE_RUN, "profile": "dev", "requested_pages": [1, 2, 3, 4, 5], "requested_rows_per_page": 20, "pages": entries}
        directory = self.root / "harness/workspace/artifacts/codex/phase0-api-quality"
        directory.mkdir(parents=True)
        self.manifest = directory / f"bizinfo-quality-{SAMPLE_RUN}.json"
        self.manifest.write_text(json.dumps({"run": self.run}))

    def load(self):
        # 합성 fixture의 checksum 교체는 테스트에서만 한다. 제품은 기존 100건의 고정 hash를 요구한다.
        digest = hashlib.sha256(self.manifest.read_bytes()).hexdigest()
        with patch("biz_aid_pipeline.ingestion.sample.SAMPLE_HASH", digest), patch.dict(os.environ, {}, clear=True):
            return load_pilot_sample(self.root)

    def test_same_sample_100_plan(self):
        data = self.load()
        self.assertEqual(len(data.items), 100)
        self.assertEqual(data.scope, SyncScope.SAMPLE)
        self.assertFalse(data.pagination_terminated)
        self.assertEqual(data.provenance["source_run_id"], SAMPLE_RUN)

    def test_wrong_manifest_hash_rejected(self):
        with self.assertRaises(PipelineError):
            load_pilot_sample(self.root)

    def test_raw_checksum_mismatch_rejected(self):
        path = self.root / f"data/raw/{SAMPLE_RUN}-page1/response.json"
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaises(PipelineError):
            self.load()

    def test_raw_symlink_rejected(self):
        path = self.root / f"data/raw/{SAMPLE_RUN}-page1/response.json"
        backup = path.with_name("original.json")
        path.rename(backup)
        path.symlink_to(backup)
        with self.assertRaises(PipelineError):
            self.load()

    def test_new_sample_or_profile_rejected(self):
        self.run["run_id"] = "different-run"
        self.manifest.write_text(json.dumps({"run": self.run}))
        with self.assertRaises(PipelineError):
            self.load()

    def test_metadata_overwrite_detected(self):
        path = self.root / f"data/raw/{SAMPLE_RUN}-page1/metadata.json"
        meta = json.loads(path.read_bytes())
        meta["byte_count"] += 1
        path.write_text(json.dumps(meta))
        with self.assertRaises(PipelineError):
            self.load()


class EnvironmentPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.dev = dict(MYSQL_DATABASE="biz_aid_dev", MYSQL_USER="chosen_dev", MYSQL_PASSWORD="synthetic-dev-password",
                        MYSQL_ROOT_PASSWORD="synthetic-root-password", MYSQL_PORT="3306")
        self.prod = dict(self.dev, MYSQL_USER="chosen_prod", MYSQL_PASSWORD="synthetic-prod-password")
        self.write(".env.dev", self.dev)
        self.write(".env.prod", self.prod)

    def write(self, name, config):
        (self.root / name).write_text("".join(f"{key}={value}\n" for key, value in config.items()))

    def test_selected_profile_only(self):
        for profile, expected in (("dev", self.dev), ("prod", self.prod)):
            self.assertEqual(profile_values(self.root, profile, set(expected), {}), expected)
        self.assertEqual(DbConfig.load(self.root, "dev", {}).user, "chosen_dev")

    def test_no_opposite_profile_generic_or_legacy_fallback(self):
        self.write(".env", self.dev)
        self.write(".env.mysql.dev", self.dev)
        for profile in ("dev", "prod"):
            with self.subTest(profile=profile):
                path = self.root / f".env.{profile}"
                content = path.read_text()
                path.unlink()
                self.assertEqual(profile_values(self.root, profile, set(self.dev), {}), {})
                if profile == "dev":
                    with self.assertRaisesRegex(PipelineError, "configuration_required"):
                        DbConfig.load(self.root, "dev", {})
                path.write_text(content)

    def test_unknown_profile_failure(self):
        for profile in ("local", "staging", "test", "", "../dev"):
            with self.assertRaisesRegex(PipelineError, "unsupported_profile"):
                profile_values(self.root, profile, set(self.dev), {})

    def test_process_precedence_both_profiles(self):
        for profile in ("dev", "prod"):
            result = profile_values(self.root, profile, set(self.dev), {"MYSQL_PASSWORD": "synthetic-os-password"})
            self.assertEqual(result["MYSQL_PASSWORD"], "synthetic-os-password")
        self.assertEqual(DbConfig.load(self.root, "dev", {"MYSQL_PASSWORD": "synthetic-os-password"}).password,
                         "synthetic-os-password")

    def test_process_empty_required_value_is_failure(self):
        with self.assertRaisesRegex(PipelineError, "MYSQL_PASSWORD"):
            DbConfig.load(self.root, "dev", {"MYSQL_PASSWORD": ""})

    def test_missing_required_setting_message_has_no_values(self):
        for key in ("MYSQL_DATABASE", "MYSQL_USER", "MYSQL_PASSWORD"):
            config = dict(self.dev)
            config.pop(key)
            self.write(".env.dev", config)
            with self.assertRaisesRegex(PipelineError, key) as failure:
                DbConfig.load(self.root, "dev", {})
            for secret in (self.dev["MYSQL_PASSWORD"], self.dev["MYSQL_ROOT_PASSWORD"]):
                self.assertNotIn(secret, str(failure.exception))

    def test_process_only_dev_without_any_env_file(self):
        (self.root / ".env.dev").unlink()
        self.assertEqual(DbConfig.load(self.root, "dev", self.dev).port, 3306)
        self.assertFalse((self.root / ".env.mysql.dev").exists())

    def test_prod_configuration_without_file_but_execution_still_forbidden(self):
        (self.root / ".env.prod").unlink()
        self.assertEqual(profile_values(self.root, "prod", set(self.prod), self.prod), self.prod)
        with self.assertRaisesRegex(PipelineError, "prod_database_access_forbidden"):
            DbConfig.load(self.root, "prod", self.prod)

    def test_port_default_and_explicit_boundary(self):
        self.dev.pop("MYSQL_PORT")
        self.write(".env.dev", self.dev)
        self.assertEqual(DbConfig.load(self.root, "dev", {}).port, 3306)
        for port in ("3307", "0", "not-a-port"):
            with self.assertRaises(PipelineError):
                DbConfig.load(self.root, "dev", {"MYSQL_PORT": port})

    def test_db_password_shell_expression_not_executed(self):
        marker = self.root / "shell-executed"
        config = DbConfig.load(self.root, "dev", {"MYSQL_PASSWORD": f"$(touch {marker})"})
        self.assertEqual(config.password, f"$(touch {marker})")
        self.assertFalse(marker.exists())
        self.assertNotIn("$(touch", repr(config))

    def test_direct_repository_config_cannot_bypass_port_boundary(self):
        from biz_aid_pipeline.persistence.mysql_repository import MysqlRepository
        with patch("biz_aid_pipeline.persistence.mysql_repository.create_engine", side_effect=AssertionError("no DB access")):
            with self.assertRaisesRegex(PipelineError, "dev_database_boundary"):
                MysqlRepository(DbConfig("127.0.0.1", 3307, "biz_aid_dev", "synthetic-user", "synthetic-password"))


class DevMysqlPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        sys.path.insert(0, str(ROOT / "infra"))
        import dev_mysql
        self.infra = dev_mysql
        self.config = dict(MYSQL_DATABASE="biz_aid_dev", MYSQL_USER="chosen_dev", MYSQL_PASSWORD="synthetic-db-secret",
                           MYSQL_ROOT_PASSWORD="synthetic-root-secret", MYSQL_PORT="3306")
        (self.root / ".env.dev").write_text("".join(f"{key}={value}\n" for key, value in self.config.items()))

    def completed(self, stdout=b"", returncode=0, stderr=b""):
        import subprocess
        return subprocess.CompletedProcess([], returncode, stdout, stderr)

    def test_explicit_profile_or_devnull_never_generic_env(self):
        command = self.infra.compose_command(self.root)
        self.assertEqual(command[command.index("--env-file") + 1], str(self.root / ".env.dev"))
        (self.root / ".env.dev").unlink()
        (self.root / ".env").write_text("MYSQL_PORT=3307\n")
        command = self.infra.compose_command(self.root)
        self.assertEqual(command[command.index("--env-file") + 1], os.devnull)

    def test_no_secret_generation_or_docker_when_configuration_missing(self):
        (self.root / ".env.dev").unlink()
        with patch.object(self.infra.subprocess, "run", side_effect=AssertionError("no Docker allowed")):
            with self.assertRaises(PipelineError):
                self.infra.prepare(self.root, {})
        self.assertEqual(list(self.root.iterdir()), [])

    def test_root_password_required_before_docker(self):
        with patch.object(self.infra.subprocess, "run", side_effect=AssertionError("no Docker allowed")):
            with self.assertRaisesRegex(PipelineError, "MYSQL_ROOT_PASSWORD"):
                self.infra.prepare(self.root, {"MYSQL_ROOT_PASSWORD": ""})

    def test_conflicting_port_requires_approval_without_stop_or_recreate(self):
        with patch.object(self.infra.subprocess, "run", return_value=self.completed()) as run:
            with patch.object(self.infra.socket, "socket") as socket:
                socket.return_value.__enter__.return_value.bind.side_effect = OSError("synthetic port conflict")
                with self.assertRaisesRegex(PipelineError, "user_approval_required"):
                    self.infra.prepare(self.root, {})
        self.assertEqual(len(run.call_args_list), 1)
        self.assertEqual(run.call_args.args[0][-3:], ["ps", "-q", "mysql"])

    def test_existing_own_host_3306_is_allowed(self):
        data = [{"State": {"Running": True}, "NetworkSettings": {"Ports": {
            "3306/tcp": [{"HostIp": "127.0.0.1", "HostPort": "3306"}]}}}]
        with patch.object(self.infra.subprocess, "run", side_effect=[self.completed(b"own-container\n"), self.completed(json.dumps(data).encode())]):
            with patch.object(self.infra.socket, "socket", side_effect=AssertionError("own listening port")):
                self.infra.port_available(self.infra.compose_command(self.root), self.root, {})

    def test_prepare_keeps_user_files_and_volume_and_uses_selected_account(self):
        before = (self.root / ".env.dev").read_bytes()
        with patch.object(self.infra, "port_available"):
            with patch.object(self.infra.subprocess, "run", return_value=self.completed(b"safe synthetic output\n")) as run:
                with patch("builtins.print"):
                    self.infra.prepare(self.root, {})
        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual(len(commands), 6)
        self.assertTrue(any("up" in command for command in commands))
        self.assertFalse(any(token in command for command in commands for token in ("down", "-v", "stop", "kill", "clean")))
        query = run.call_args_list[1].kwargs["input"]
        self.assertIn(b"'chosen_dev'@'%'", query)
        self.assertIn("-h127.0.0.1 --protocol=TCP", commands[1][-1])
        self.assertNotIn(b"ALTER USER", query)
        self.assertNotIn(b"IDENTIFIED BY", query)
        for call in run.call_args_list:
            self.assertEqual(call.kwargs["env"]["MYSQL_PORT"], "3306")
            self.assertEqual(call.kwargs["env"]["COMPOSE_DISABLE_ENV_FILE"], "1")
        self.assertEqual((self.root / ".env.dev").read_bytes(), before)
        self.assertFalse((self.root / ".env.mysql.dev").exists())

    def test_secret_output_suppressed_on_failure(self):
        import contextlib
        import io
        output = io.StringIO()
        reflection = (self.config["MYSQL_PASSWORD"] + self.config["MYSQL_ROOT_PASSWORD"]).encode()
        with patch.object(self.infra, "port_available"), patch.object(self.infra.subprocess, "run", return_value=self.completed(reflection, 1, reflection)):
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output), self.assertRaises(PipelineError) as failure:
                self.infra.prepare(self.root, {})
        log = (self.root / "harness/workspace/artifacts/codex/infra-dev-mysql/logs/preparation.log").read_text()
        for secret in (self.config["MYSQL_PASSWORD"], self.config["MYSQL_ROOT_PASSWORD"]):
            self.assertNotIn(secret, log + output.getvalue() + str(failure.exception))

    def test_encoded_secret_success_output_withheld(self):
        from urllib.parse import quote
        config = dict(self.config, MYSQL_PASSWORD='synthetic/"$secret')
        for raw in (config["MYSQL_PASSWORD"].encode(), quote(config["MYSQL_PASSWORD"], safe="").encode(),
                    json.dumps(config["MYSQL_PASSWORD"])[1:-1].encode()):
            self.assertIn(b"REDACTED", self.infra.sanitized_output(raw, config))

    def test_product_config_has_no_retired_dependencies(self):
        retired_file = ".env." + "mysql.dev"
        retired_port = str(13000 + 306)
        for name in ("infra/dev_mysql.py", "docker-compose.yml", "data-pipeline/src/biz_aid_pipeline/config/settings.py"):
            content = (ROOT / name).read_text()
            self.assertNotIn(retired_file, content)
            self.assertNotIn(retired_port, content)


class DatabaseCommentContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ROOT / "scripts/lib"))
        from validate import database_comment_problem, database_comments
        cls.problem = staticmethod(database_comment_problem)
        cls.check = staticmethod(database_comments)

    def test_empty_comments_fail(self):
        for value in (None, "", " \t\n "):
            self.assertEqual(self.problem("field", value), "missing")

    def test_placeholder_and_repeated_names_fail(self):
        for value in ("TODO: 설명 추가", "TBD", "데이터", "값.", "source_active", "Source Active"):
            self.assertEqual(self.problem("source_active", value), "placeholder_or_name_only")

    def test_korean_meaning_required(self):
        self.assertEqual(self.problem("field", "Application source value"), "korean_description_required")
        self.assertIsNone(self.problem("field", "공고 원문의 신청기간. FREE_TEXT를 변형 없이 보존한다."))

    def connection(self, schema="biz_aid_test", table_comment="합성 추천 실행 기록을 보존하는 업무 테이블", column_comment="합성 추천 실행의 UTC 시작 시각"):
        from unittest.mock import MagicMock
        con = MagicMock()
        database, tables, columns = MagicMock(), MagicMock(), MagicMock()
        database.scalar_one.return_value = schema
        tables.mappings.return_value.all.return_value = [{"TABLE_NAME": "future_recommendation_history", "TABLE_COMMENT": table_comment}]
        columns.mappings.return_value.all.return_value = [{"TABLE_NAME": "future_recommendation_history", "COLUMN_NAME": "started_at", "COLUMN_COMMENT": column_comment}]
        con.execute.side_effect = [database, tables, columns]
        con.table_result = tables
        return con

    def test_future_table_is_checked_without_name_allowlist(self):
        con = self.connection()
        result = self.check(con)
        self.assertEqual((result["table_count"], result["column_count"], result["failures"]), (1, 1, []))
        for call in con.execute.call_args_list[1:]:
            query = str(call.args[0])
            self.assertIn("flyway_schema_history", query)
            self.assertNotIn("support_programs", query)
            self.assertEqual(call.args[1], {"schema": "biz_aid_test"})

    def test_new_missing_table_and_column_fail(self):
        result = self.check(self.connection(table_comment="", column_comment=" "))
        self.assertEqual(result["failures"], [
            {"object": "future_recommendation_history", "reason": "missing"},
            {"object": "future_recommendation_history.started_at", "reason": "missing"}])

    def test_prod_or_system_schema_rejected_before_metadata_query(self):
        for schema in ("mysql", "information_schema", "performance_schema", "sys", "biz_aid_prod", None):
            con = self.connection(schema=schema)
            with self.assertRaises(ValueError):
                self.check(con)
            self.assertEqual(con.execute.call_count, 1)

    def test_empty_schema_does_not_fake_pass(self):
        con = self.connection()
        con.table_result.mappings.return_value.all.return_value = []
        with self.assertRaises(ValueError):
            self.check(con)

    def test_failure_does_not_echo_comment_content(self):
        result = self.check(self.connection(column_comment="synthetic-test-secret"))
        self.assertTrue(result["failures"])
        self.assertNotIn("synthetic-test-secret", json.dumps(result))

    def test_applied_v1_is_immutable(self):
        expected = "3c27534e7ff42382a46623575ee6b0c7e8e5cd6dc6c0a3671511277ee85faf8a"
        self.assertEqual(hashlib.sha256((ROOT / "migrations/V1__structured_support_programs.sql").read_bytes()).hexdigest(), expected)
