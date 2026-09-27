import copy
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError
from urllib.parse import parse_qs, quote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import bizinfo_probe as probe
import phase0
import phase0_api_quality as quality

SYNTHETIC_KEY = "synthetic-quality-key+/="


class ApiQualityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.env = {"BIZINFO_SERVICE_KEY": SYNTHETIC_KEY}
        sample = phase0.read_json(ROOT / "tests/fixtures/external-api/bizinfo-user-sample.json")
        self.base = sample["response"]["body"]["items"]["item"][0]
        self.urls = []

    def payload(self, page):
        items = []
        for offset in range(20):
            index = (page - 1) * 20 + offset
            item = copy.deepcopy(self.base)
            item["pblancId"] = f"SYNTHETIC_{index:03}"
            item["creatPnttm"] = (datetime(2026, 9, 23, 20) - timedelta(minutes=index)).strftime("%Y-%m-%d %H:%M:%S")
            items.append(item)
        return {"response": {"header": {"resultCode": "00", "resultMsg": "NORMAL_SERVICE"},
                             "body": {"items": {"item": items}, "pageNo": page, "numOfRows": 20, "totalCount": 1200}}}

    def fake(self, url):
        self.urls.append(url)
        params = parse_qs(urlsplit(url).query)
        self.assertEqual(params["serviceKey"], [SYNTHETIC_KEY])
        self.assertEqual(params["numOfRows"], ["20"])
        return 200, json.dumps(self.payload(int(params["pageNo"][0])), ensure_ascii=False).encode()

    def collect(self, identifier="quality-run", fetch=None):
        return quality.collect(self.root, "dev", identifier, self.env, fetch or self.fake)

    def test_fixed_five_by_twenty_plan_and_page_sum(self):
        result = self.collect()
        self.assertEqual([parse_qs(urlsplit(u).query)["pageNo"] for u in self.urls], [[str(n)] for n in range(1, 6)])
        self.assertEqual(result["run"]["http_requests_attempted"], 5)
        self.assertEqual(result["run"]["successful_pages"], [1, 2, 3, 4, 5])
        self.assertEqual(result["run"]["collection_status"], "COMPLETED")
        self.assertEqual(result["metrics"]["actual_items"], 100)
        self.assertEqual(result["metrics"]["pblancId"]["unique_count"], 100)
        self.assertEqual(result["metrics"]["ordering"]["all_received"], "observed_descending")
        self.assertTrue(all(b["ordering"] == "observed_descending" for b in result["metrics"]["ordering"]["boundaries"]))

    def test_duplicate_ids_are_detected_without_removing_rows(self):
        def fetch(url):
            page = int(parse_qs(urlsplit(url).query)["pageNo"][0])
            payload = self.payload(page)
            if page == 3:
                payload["response"]["body"]["items"]["item"][0]["pblancId"] = "SYNTHETIC_000"
            return 200, json.dumps(payload).encode()
        metrics = self.collect(fetch=fetch)["metrics"]
        self.assertEqual(metrics["actual_items"], 100)
        self.assertEqual(metrics["pblancId"]["unique_count"], 99)
        self.assertEqual(metrics["pblancId"]["duplicate_extra_count"], 1)
        self.assertEqual(metrics["pblancId"]["duplicated_id_count"], 1)
        self.assertEqual([p["page"] for p in metrics["pblancId"]["duplicates"][0]["locations"]], [1, 3])

    def test_missing_null_blank_invalid_are_separate_and_rows_are_retained(self):
        def fetch(url):
            page = int(parse_qs(urlsplit(url).query)["pageNo"][0])
            payload = self.payload(page)
            if page == 1:
                items = payload["response"]["body"]["items"]["item"]
                for field in ("pblancNm", "pblancId"):
                    items[0].pop(field)
                    items[1][field] = None
                    items[2][field] = " \t "
                    items[3][field] = 123
            return 200, json.dumps(payload).encode()
        result = self.collect(fetch=fetch)
        self.assertEqual(result["run"]["collection_status"], "COMPLETED")
        self.assertEqual(result["metrics"]["actual_items"], 100)
        for field in ("pblancNm", "pblancId"):
            measured = result["metrics"]["fields"][field]
            self.assertEqual(measured["counts"], {"VALID": 96, "MISSING": 1, "NULL": 1, "BLANK": 1, "INVALID": 1})
            self.assertEqual(measured["ratios"]["NULL"], 0.01)
        self.assertEqual(result["metrics"]["pblancId"]["key_presence_rate"], 0.99)
        self.assertEqual(result["metrics"]["pblancId"]["usable_id_rate"], 0.96)

    def test_total_count_change_is_observation_not_collection_failure(self):
        def fetch(url):
            page = int(parse_qs(urlsplit(url).query)["pageNo"][0])
            payload = self.payload(page)
            payload["response"]["body"]["totalCount"] += page
            return 200, json.dumps(payload).encode()
        result = self.collect(fetch=fetch)
        self.assertEqual(result["run"]["collection_status"], "COMPLETED")
        self.assertTrue(result["metrics"]["pagination"]["totalCount_changed"])
        self.assertEqual(result["run"]["observed_total_counts"], [1201, 1202, 1203, 1204, 1205])

    def test_period_categories_preserve_raw_and_separate_unavailable_reasons(self):
        cases = [({}, "MISSING"), ({"reqstBeginEndDe": None}, "MISSING"),
                 ({"reqstBeginEndDe": "  "}, "MISSING"), ({"reqstBeginEndDe": 123}, "INVALID"),
                 ({"reqstBeginEndDe": " 2026-09-23 ~ 2026-10-08 "}, "DATE_RANGE"),
                 ({"reqstBeginEndDe": "예산 소진시까지"}, "FREE_TEXT"),
                 ({"reqstBeginEndDe": "2026-02-31 ~ 2026-03-02"}, "INVALID"),
                 ({"reqstBeginEndDe": "2026-10-08 ~ 2026-09-23"}, "INVALID")]
        for item, expected in cases:
            before = copy.deepcopy(item)
            self.assertEqual(quality.period_category(item), expected)
            self.assertEqual(item, before)

    def test_at_filename_split_and_unknown_extension_count(self):
        def fetch(url):
            page = int(parse_qs(urlsplit(url).query)["pageNo"][0])
            payload = self.payload(page)
            for item in payload["response"]["body"]["items"]["item"]:
                item["fileNm"] = "A.PDF@B.hwp@C.HWPX@D.Zip@E.xyz@README@"
            return 200, json.dumps(payload).encode()
        measured = self.collect(fetch=fetch)["metrics"]["filename_extensions"]["fileNm"]
        self.assertEqual(measured["denominator"], 700)
        self.assertEqual(measured["counts"], {"PDF": 100, "HWP": 100, "HWPX": 100, "ZIP": 100, "OTHER": 100, "UNKNOWN": 200})

    def test_partial_http_page_failure_preserves_raw_and_next_action(self):
        def fetch(url):
            params = parse_qs(urlsplit(url).query)
            if params["pageNo"] == ["3"]:
                self.urls.append(url)
                return 503, b"<synthetic-error/>"
            return self.fake(url)
        result = self.collect(fetch=fetch)
        self.assertEqual(len(self.urls), 5)
        self.assertEqual(result["run"]["failed_pages"], [3])
        self.assertEqual(result["run"]["successful_pages"], [1, 2, 4, 5])
        self.assertEqual(result["run"]["collection_status"], "PARTIAL_FAILED")
        self.assertEqual(result["metrics"]["actual_items"], 80)
        self.assertEqual(result["metrics"]["fields"]["pblancId"]["denominator"], 80)
        self.assertEqual(result["metrics"]["pagination"]["missing_pages"], [3])
        self.assertIn("preserve_raw", result["run"]["next_action"])
        phase0.verify_snapshot(self.root / result["run"]["pages"][2]["raw_snapshot"])

    def test_no_credential_is_unmeasured_and_no_http(self):
        result = quality.collect(self.root, "dev", "no-key", {}, lambda url: self.fail("unexpected HTTP"))
        self.assertEqual(result["run"]["collection_status"], "NOT_RUN")
        self.assertEqual(result["metrics"]["fields"]["pblancId"]["status"], "UNMEASURED")
        self.assertIsNone(result["metrics"]["fields"]["pblancId"]["counts"]["NULL"])
        self.assertIsNone(result["metrics"]["pblancId"]["unique_count"])

    def test_wrong_echo_and_oversized_page_are_contract_errors(self):
        for number, oversized in ((1, False), (2, True)):
            def fetch(url):
                page = int(parse_qs(urlsplit(url).query)["pageNo"][0])
                payload = self.payload(page)
                if page == number:
                    if oversized:
                        payload["response"]["body"]["items"]["item"].append(copy.deepcopy(self.base))
                    else:
                        payload["response"]["body"]["pageNo"] = 5
                return 200, json.dumps(payload).encode()
            result = self.collect(f"wrong-{number}", fetch)
            self.assertEqual(result["run"]["pages"][number-1]["outcome"], "CONTRACT_ERROR")
            self.assertEqual(result["metrics"]["actual_items"], 80)

    def test_short_page_is_recorded_as_incomplete_without_filling_rows(self):
        def fetch(url):
            page = int(parse_qs(urlsplit(url).query)["pageNo"][0])
            payload = self.payload(page)
            if page == 5:
                payload["response"]["body"]["items"]["item"].pop()
            return 200, json.dumps(payload).encode()
        result = self.collect(fetch=fetch)
        self.assertEqual(result["run"]["collection_status"], "INCOMPLETE")
        self.assertEqual(result["metrics"]["actual_items"], 99)
        self.assertEqual(result["metrics"]["pagination"]["item_count_mismatches"], [{"page": 5, "received": 19}])

    def test_repeat_and_partial_raw_collision_fail_before_network(self):
        self.collect("repeat")
        with self.assertRaises(probe.ProbeError):
            self.collect("repeat", lambda url: self.fail("repeat HTTP"))
        (self.root / "data/raw/partial-page5").mkdir()
        with self.assertRaises(probe.ProbeError):
            self.collect("partial", lambda url: self.fail("partial HTTP"))

    def test_network_exception_and_reflected_key_cannot_leak(self):
        def failing(url):
            raise URLError(url)
        result = self.collect("network", failing)
        self.assertTrue(all(p["outcome"] == "TRANSPORT_ERROR" for p in result["run"]["pages"]))
        reflected = self.collect("reflected", lambda url: (200, json.dumps({"key": SYNTHETIC_KEY}).encode()))
        self.assertTrue(all(p["raw_snapshot"] is None for p in reflected["run"]["pages"]))
        for value in (result, reflected):
            self.assertNotIn(SYNTHETIC_KEY, json.dumps(value))
            self.assertNotIn(quote(SYNTHETIC_KEY, safe=""), json.dumps(value))

    def test_success_stdout_report_and_log_do_not_contain_key(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(probe, "http_get", side_effect=self.fake):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = quality.main(["collect", "--profile", "dev", "--run-id", "safe"], self.root, self.env)
        self.assertEqual(code, 0)
        result = phase0.read_json(self.root / "harness/workspace/artifacts/bizinfo-quality-safe.json")
        for value in (stdout.getvalue()+stderr.getvalue(), json.dumps(result), quality.render(result)):
            self.assertNotIn(SYNTHETIC_KEY, value)
            self.assertNotIn(quote(SYNTHETIC_KEY, safe=""), value)
            self.assertNotIn("serviceKey=", value)

    def test_offline_analysis_is_deterministic_and_checksum_changes_fail(self):
        result = self.collect()
        self.assertEqual(quality.analyze(result["run"], self.root), result["metrics"])
        raw = self.root / "data/raw/quality-run-page1/response.json"
        raw.write_bytes(raw.read_bytes()+b" ")
        with self.assertRaisesRegex(ValueError, "checksum"):
            quality.analyze(result["run"], self.root)

    def test_prod_is_rejected_before_loading_any_secret_or_http(self):
        with patch.object(probe, "load_config", side_effect=AssertionError("profile read")):
            with self.assertRaisesRegex(probe.ProbeError, "must_be_dev"):
                quality.collect(self.root, "prod", "forbidden-prod", self.env, self.fake)

    def test_positive_batch_no_data_is_api_error_not_expected_negative(self):
        raw = json.dumps({"response": {"header": {"resultCode": "03", "resultMsg": "NODATA_ERROR"},
                                      "body": {"items": {}, "numOfRows": 0, "pageNo": 1, "totalCount": 0}}}).encode()
        result = self.collect(fetch=lambda url: (200, raw))
        self.assertEqual(result["run"]["collection_status"], "FAILED")
        self.assertTrue(all(p["outcome"] == "API_ERROR" for p in result["run"]["pages"]))


if __name__ == "__main__":
    unittest.main()
