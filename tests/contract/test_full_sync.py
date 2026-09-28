import copy
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import URLError
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data-pipeline/src"))
from biz_aid_pipeline.bizinfo.client import BizinfoClient
from biz_aid_pipeline.bizinfo.raw_snapshot import verify_full_snapshot
from biz_aid_pipeline.config.settings import ApiConfig, PipelineError
from biz_aid_pipeline.ingestion.full_sync import ARTIFACT_ROOT, add_full_metrics, preflight, run_full_sync, validate_full_report
from biz_aid_pipeline import full_cli

KEY = "synthetic-full-key+/="


def fixture_root(root):
    for name in ("contracts/external-api/bizinfo.contract.json", "contracts/schemas/full-structured-sync.contract.json",
                 "contracts/schemas/structured-data-quality.contract.json"):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, path)


def responses(prefix="SYNTHETIC_FULL", count=45, transform=None):
    def transport(url):
        query = parse_qs(urlsplit(url).query)
        number, rows = int(query["pageNo"][0]), int(query["numOfRows"][0])
        if query["serviceKey"] != [KEY] or "updtPnttm" in query or "pblancId" in query:
            raise AssertionError("wrong full request boundary")
        items = [{"pblancId": f"{prefix}_{i}", "pblancNm": "합성 FULL 공고", "reqstBeginEndDe": "예산 소진시까지"}
                 for i in range((number - 1) * rows, min(number * rows, count))]
        payload = {"response": {"header": {"resultCode": "00", "resultMsg": "NORMAL_SERVICE"},
            "body": {"items": {"item": items}, "pageNo": number, "numOfRows": rows, "totalCount": count}}}
        if transform:
            payload = transform(number, payload)
        return 200, json.dumps(payload, ensure_ascii=False).encode()
    return transport


class FullAcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        fixture_root(self.root)
        self.env = patch.dict(os.environ, {"BIZINFO_SERVICE_KEY": KEY}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)

    def client(self, transport=None):
        return BizinfoClient(ApiConfig.load(self.root, "dev"), self.root, transport or responses())

    def failure(self, transport, expected_reason):
        factory = Mock(side_effect=AssertionError("incomplete FULL must not enter DB"))
        result = run_full_sync(self.root, "dev", "failed-full", transport=transport, repository_factory=factory)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn(expected_reason, result["reconciliation_skipped_reason"])
        self.assertFalse(result["reconciliation_executed"])
        self.assertIsNone(result["soft_delete_candidate_count"])
        self.assertEqual(result["soft_deleted"], 0)
        factory.assert_not_called()
        validate_full_report(result, self.root)
        provenance = json.loads((self.root / ARTIFACT_ROOT / "failed-full/acquisition.json").read_text())
        self.assertEqual(preflight(verify_full_snapshot(self.root, "failed-full", provenance, KEY), "failed-full")["status"], "FAIL")
        return result

    def test_multi_page_full_and_final_partial(self):
        batch = self.client().scan_full()
        self.assertEqual([len(p.items) for p in batch.pages], [20, 20, 5])
        self.assertTrue(batch.pagination_terminated)
        report = preflight(batch, "full")
        self.assertEqual((report["status"], report["expected_total_count"], report["unique_pblanc_id_count"]), ("PASS", 45, 45))

    def test_exact_last_full_page_no_extra_negative_request(self):
        transport = Mock(side_effect=responses(count=40))
        batch = self.client(transport).scan_full()
        self.assertEqual(len(batch.pages), 2)
        self.assertEqual(transport.call_count, 2)
        self.assertEqual(preflight(batch, "exact")["status"], "PASS")

    def test_duplicate_ids_fail_before_db(self):
        def transform(number, value):
            if number == 2:
                value["response"]["body"]["items"]["item"][0]["pblancId"] = "SYNTHETIC_FULL_0"
            return value
        result = self.failure(responses(transform=transform), "duplicate_count")
        self.assertEqual(result["duplicate_count"], 1)

    def test_invalid_identifier_before_normalization_db(self):
        def transform(number, value):
            if number == 1:
                value["response"]["body"]["items"]["item"][0]["pblancId"] = "invalid space"
            return value
        self.assertEqual(self.failure(responses(transform=transform), "invalid_pblanc_id_count")["invalid_pblanc_id_count"], 1)

    def test_page_transport_failure_raw_other_pages_preserved(self):
        transport = responses()
        def broken(url):
            if parse_qs(urlsplit(url).query)["pageNo"] == ["2"]:
                raise URLError(KEY)
            return transport(url)
        result = self.failure(broken, "transport_errors")
        self.assertEqual((result["requested_page_count"], result["successful_page_count"], result["failed_page_count"]), (2, 1, 1))
        self.assertTrue((self.root / "data/raw/failed-full/page-000001/response.json").is_file())

    def test_positive_no_data_is_api_failure_and_raw_preserved(self):
        def transform(number, value):
            if number == 2:
                value["response"]["header"] = {"resultCode": "03", "resultMsg": "NODATA_ERROR"}
                value["response"]["body"].update(items={}, totalCount=0, numOfRows=0)
            return value
        self.failure(responses(transform=transform), "api_errors")
        self.assertTrue((self.root / "data/raw/failed-full/page-000002/response.json").is_file())

    def test_total_count_change_fails(self):
        def transform(number, value):
            if number == 2:
                value["response"]["body"]["totalCount"] = 46
            return value
        self.failure(responses(transform=transform), "totalCount_not_consistent")

    def test_observed_count_mismatch_fails(self):
        def transform(number, value):
            if number == 3:
                value["response"]["body"]["items"]["item"].pop()
            return value
        self.failure(responses(transform=transform), "unique_count_totalCount_mismatch")

    def test_empty_page_anomaly(self):
        def transform(number, value):
            if number == 2:
                value["response"]["body"]["items"]["item"] = []
            return value
        self.failure(responses(transform=transform), "page_item_count_anomaly")

    def test_limit_prevents_incomplete_universe_success(self):
        result = self.client(responses(count=41)).scan_full(max_pages=2)
        self.assertFalse(result.pagination_terminated)
        self.assertEqual(len(result.pages), 1)
        self.assertEqual(preflight(result, "bounded")["status"], "FAIL")

    def test_secret_reflection_no_raw_or_logs(self):
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            result = self.failure(lambda url: (200, KEY.encode()), "contract_errors")
        self.assertNotIn(KEY, output.getvalue() + json.dumps(result))
        self.assertFalse((self.root / "data/raw/failed-full/page-000001").exists())
        for path in self.root.rglob("*"):
            if path.is_file():
                self.assertNotIn(KEY.encode(), path.read_bytes())

    def test_missing_credential_no_api_or_db(self):
        with patch.dict(os.environ, {"BIZINFO_SERVICE_KEY": ""}, clear=True):
            transport, repository = Mock(), Mock()
            with self.assertRaises(PipelineError):
                run_full_sync(self.root, "dev", "missing", transport=transport, repository_factory=repository)
            transport.assert_not_called()
            repository.assert_not_called()

    def test_prod_forbidden_before_secret_read(self):
        with patch.object(ApiConfig, "load") as load, self.assertRaises(PipelineError):
            run_full_sync(self.root, "prod", "prod")
        load.assert_not_called()

    def test_cli_prod_apply_and_secret_arguments_never_echo(self):
        for arguments in (["collect", "--profile", "prod", "--run-id", KEY],
                ["collect", "--profile", "dev", "--run-id", "safe", "--apply"], ["collect", "--serviceKey", KEY]):
            output = io.StringIO()
            with redirect_stdout(output), redirect_stderr(output):
                self.assertEqual(full_cli.main(arguments), 1)
            self.assertNotIn(KEY, output.getvalue())

    def test_checksum_overwrite_and_manifest_integrity(self):
        def invalid(number, value):
            value["response"]["body"]["items"]["item"] = []
            return value
        self.failure(responses(transform=invalid), "page_item_count_anomaly")
        with self.assertRaises(FileExistsError):
            run_full_sync(self.root, "dev", "failed-full", transport=responses())
        path = self.root / "data/raw/failed-full/page-000001/response.json"
        path.write_bytes(b"tampered")
        provenance = json.loads((self.root / ARTIFACT_ROOT / "failed-full/acquisition.json").read_text())
        with self.assertRaises(PipelineError):
            verify_full_snapshot(self.root, "failed-full", provenance, KEY)

    def test_normalization_failure_does_not_enter_db(self):
        def transform(number, value):
            value["response"]["body"]["items"]["item"][0]["inqireCo"] = "not-an-integer"
            return value
        self.assertGreater(self.failure(responses(transform=transform), "normalization_fatal_errors")["normalization_fatal_errors"], 0)

    def test_page_echo_mismatch_before_db(self):
        def transform(number, value):
            value["response"]["body"]["pageNo"] = number + 1
            return value
        self.failure(responses(transform=transform), "contract_errors")

    def test_checkpoint_counts_and_safe_local_recovery(self):
        transport = responses()
        def broken(url):
            if parse_qs(urlsplit(url).query)["pageNo"] == ["2"]:
                raise URLError("synthetic failure")
            return transport(url)
        self.failure(broken, "transport_errors")
        paths = sorted((self.root / "harness/workspace/checkpoints").glob("*.md"))
        self.assertEqual(len(paths), 4)
        last = json.loads(paths[-1].read_text().split("```json\n", 1)[1].split("\n```", 1)[0])
        self.assertEqual((last["total_target"], last["completed_count"], last["failed_count"]), (3, 1, 1))
        self.assertEqual(last["resume_command"], "python3 -B scripts/run_full_sync.py verify --run-id failed-full")
        self.assertEqual(last["failed_items"][0]["item_id"], 2)

    def test_full_report_rejects_false_pass_and_delete(self):
        batch = self.client().scan_full()
        report = preflight(batch, "quality")
        report.update(noop=45, reconciliation_dry_run=True, soft_delete_candidate_count=0,
                      soft_delete_candidate_pblanc_ids=[], mysql_final_row_count=45,
                      reconciliation_skipped_reason=["dry_run_only"])
        add_full_metrics(report, batch, {"status": "PASS"})
        report.update(transaction_seconds_limit=60, db_phase_elapsed_seconds=0.1)
        validate_full_report(report, self.root)
        for change in ({"raw_snapshot_validation": "FAIL"}, {"requested_page_count": 2},
                {"mysql_final_row_count": 44}, {"soft_delete_candidate_count": 1},
                {"raw_item_count": 46}, {"soft_deleted": 1}, {"acquisition_status": "FAIL"}):
            with self.subTest(change=change), self.assertRaises(PipelineError):
                validate_full_report(dict(report, **change), self.root)


if __name__ == "__main__":
    unittest.main()
