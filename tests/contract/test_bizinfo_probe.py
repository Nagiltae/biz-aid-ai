import copy
import hashlib
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from http.client import BadStatusLine
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import bizinfo_probe as probe
import phase0

FIXTURE = ROOT / "tests/fixtures/external-api/bizinfo-user-sample.json"
SYNTHETIC_KEY = "synthetic-probe-key+/="


class BizinfoResponseContractTests(unittest.TestCase):
    def setUp(self):
        self.payload = phase0.read_json(FIXTURE)

    def test_real_user_sample_matches_contract_and_provenance_checksum(self):
        spec = probe.contract()
        self.assertEqual(hashlib.sha256(FIXTURE.read_bytes()).hexdigest(), spec["evidence"]["fixture_sha256"])
        self.assertEqual(spec["evidence"]["kind"], "user_provided_sanitized_real_sample")
        self.assertIs(probe.validate_response(self.payload), self.payload)
        self.assertEqual(len(self.payload["response"]["body"]["items"]["item"]), 10)
        self.assertEqual(self.payload["response"]["body"]["totalCount"], 1518)

    def test_header_fields_require_strings(self):
        for name in ("resultCode", "resultMsg"):
            for value in (None, 0, "", True):
                with self.subTest(name=name, value=value):
                    payload = copy.deepcopy(self.payload)
                    payload["response"]["header"][name] = value
                    with self.assertRaises(probe.ProbeError):
                        probe.validate_response(payload)

    def test_non_success_result_code_is_not_a_successful_collection(self):
        self.payload["response"]["header"] = {"resultCode": "99", "resultMsg": "synthetic error"}
        self.payload["response"].pop("body")
        self.assertEqual(probe.validate_header(self.payload)["resultCode"], "99")
        with self.assertRaisesRegex(probe.ProbeError, "api_error"):
            probe.validate_response(self.payload)

    def test_incorrect_response_body_items_and_item_envelopes_fail(self):
        variants = [
            {}, {"response": []}, {"response": {"header": {}}},
            {"response": {"header": self.payload["response"]["header"], "body": []}},
        ]
        for item_value in (None, "", {}, ["invalid"]):
            payload = copy.deepcopy(self.payload)
            payload["response"]["body"]["items"]["item"] = item_value
            variants.append(payload)
        for items_value in (None, "", []):
            payload = copy.deepcopy(self.payload)
            payload["response"]["body"]["items"] = items_value
            variants.append(payload)
        for payload in variants:
            with self.subTest(payload_type=type(payload).__name__):
                with self.assertRaises(probe.ProbeError):
                    probe.validate_response(payload)

    def test_pagination_fields_reject_wrong_types_and_bounds(self):
        for name in ("pageNo", "numOfRows", "totalCount"):
            for value in ("10", None, True, -1, 1.5):
                with self.subTest(name=name, value=value):
                    payload = copy.deepcopy(self.payload)
                    payload["response"]["body"][name] = value
                    with self.assertRaisesRegex(probe.ProbeError, "invalid_pagination_field"):
                        probe.validate_response(payload)

    def test_identifier_missing_null_or_blank_is_rejected(self):
        for value in (None, "", "  ", 123):
            payload = copy.deepcopy(self.payload)
            payload["response"]["body"]["items"]["item"][0]["pblancId"] = value
            with self.assertRaises(probe.ProbeError):
                probe.validate_response(payload)
        self.payload["response"]["body"]["items"]["item"][0].pop("pblancId")
        with self.assertRaisesRegex(probe.ProbeError, "missing_identifier"):
            probe.validate_response(self.payload)

    def test_observed_nullable_fields_and_raw_exceptions_are_preserved(self):
        before = copy.deepcopy(self.payload)
        items = self.payload["response"]["body"]["items"]["item"]
        self.assertIsNone(items[3]["flpthNm"])
        self.assertIsNone(items[3]["fileNm"])
        self.assertIsNone(items[3]["rceptEngnHmpgUrl"])
        self.assertEqual(items[8]["reqstBeginEndDe"], "예산 소진시까지")
        self.assertIn("<p", items[0]["bsnsSumryCn"])
        self.assertIn("@", items[1]["flpthNm"])
        self.assertIn("@", items[1]["fileNm"])
        self.assertIn("\r\n", items[2]["reqstMthPapersCn"])
        probe.validate_response(self.payload)
        self.assertEqual(self.payload, before)

    def test_unknown_fields_at_every_layer_survive_raw_validation(self):
        self.payload["unknown_top"] = {"future": [1, None]}
        self.payload["response"]["unknown_response"] = True
        self.payload["response"]["header"]["unknown_header"] = "extra"
        self.payload["response"]["body"]["unknown_body"] = {"nested": "value"}
        self.payload["response"]["body"]["items"]["unknown_items"] = []
        self.payload["response"]["body"]["items"]["item"][0]["unknown_item"] = {"raw": "<b>value</b>"}
        before = copy.deepcopy(self.payload)
        probe.validate_response(self.payload)
        self.assertEqual(self.payload, before)

    def test_empty_array_is_only_an_accepted_local_shape_not_an_api_guarantee(self):
        self.payload["response"]["body"]["items"]["item"] = []
        self.payload["response"]["body"]["totalCount"] = 0
        probe.validate_response(self.payload)
        self.assertEqual(probe.contract()["response"]["empty_result_shape"], "unconfirmed")

    def test_optional_observed_fields_are_not_claimed_globally_required(self):
        item = self.payload["response"]["body"]["items"]["item"][0]
        self.payload["response"]["body"]["items"]["item"] = [{"pblancId": item["pblancId"]}]
        probe.validate_response(self.payload)
        for field in probe.contract()["response"]["item_fields"].values():
            self.assertIsNone(field["official_required"])

    def test_sample_ordering_is_observed_without_newest_first_guarantee(self):
        values = [item["creatPnttm"] for item in self.payload["response"]["body"]["items"]["item"]]
        self.assertEqual(probe.ordering(values), "observed_descending")
        self.assertEqual(probe.ordering(list(reversed(values))), "observed_ascending")
        self.assertEqual(probe.ordering([values[0], None]), "unconfirmed_timestamp_format")
        self.assertEqual(probe.contract()["response"]["ordering_guarantee"], "unconfirmed")


class BizinfoProfileTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()

    def write_profile(self, profile, key):
        path = self.root / f".env.{profile}"
        path.write_text(f"BIZINFO_SERVICE_KEY={key}\nBIZINFO_DATA_TYPE=json\n", encoding="utf-8")
        return path

    def test_selected_profile_is_the_only_secret_file_read(self):
        for profile, other in (("dev", "prod"), ("prod", "dev")):
            with self.subTest(profile=profile):
                selected = self.write_profile(profile, f"synthetic-{profile}-key")
                forbidden = self.write_profile(other, "synthetic-other-key")
                read_text = Path.read_text
                accessed = []
                def guarded_read(path, *args, **kwargs):
                    self.assertNotEqual(path, forbidden, "unselected profile was read")
                    accessed.append(path)
                    return read_text(path, *args, **kwargs)
                with patch.object(Path, "read_text", guarded_read):
                    config = probe.load_config(self.root, profile, {})
                self.assertEqual(config["key"], f"synthetic-{profile}-key")
                self.assertEqual(config["profile"], profile)
                self.assertIn(selected, accessed)

    def test_unsupported_profile_is_rejected_before_reading_files(self):
        for profile in ("local", "staging", "test", "../prod", "", None):
            with self.subTest(profile=profile):
                with patch.object(Path, "read_text", side_effect=AssertionError("unexpected read")):
                    with self.assertRaisesRegex(probe.ProbeError, "unsupported_profile"):
                        probe.load_config(self.root, profile, {})

    def test_dev_never_falls_back_to_prod_or_legacy_env(self):
        self.write_profile("prod", "synthetic-prod-only")
        (self.root / ".env").write_text("BIZINFO_SERVICE_KEY=synthetic-legacy\n", encoding="utf-8")
        self.assertEqual(probe.load_config(self.root, "dev", {})["key"], "")

    def test_prod_never_falls_back_to_dev_or_legacy_env(self):
        self.write_profile("dev", "synthetic-dev-only")
        (self.root / ".env").write_text("BIZINFO_SERVICE_KEY=synthetic-legacy\n", encoding="utf-8")
        self.assertEqual(probe.load_config(self.root, "prod", {})["key"], "")

    def test_process_environment_overrides_each_selected_file(self):
        for profile in ("dev", "prod"):
            self.write_profile(profile, "synthetic-file-key")
            env = {"BIZINFO_SERVICE_KEY": SYNTHETIC_KEY, "BIZINFO_DATA_TYPE": "json",
                   "BIZINFO_API_BASE_URL": probe.contract()["request"]["endpoint"]}
            self.assertEqual(probe.load_config(self.root, profile, env)["key"], SYNTHETIC_KEY)
            self.assertEqual(probe.load_config(self.root, profile, {"BIZINFO_SERVICE_KEY": ""})["key"], "")

    def test_app_profile_is_not_a_probe_selector(self):
        self.write_profile("dev", "synthetic-dev-key")
        self.write_profile("prod", "synthetic-prod-key")
        config = probe.load_config(self.root, "dev", {"APP_PROFILE": "prod"})
        self.assertEqual(config["profile"], "dev")
        self.assertEqual(config["key"], "synthetic-dev-key")

    def test_shell_expressions_and_export_are_never_executed(self):
        marker = self.root / "must-not-exist"
        path = self.write_profile("dev", f"$(touch {marker})")
        self.assertEqual(probe.load_config(self.root, "dev", {})["key"], f"$(touch {marker})")
        path.write_text(f"export BIZINFO_SERVICE_KEY='`touch {marker}`'\n", encoding="utf-8")
        self.assertEqual(probe.load_config(self.root, "dev", {})["key"], f"`touch {marker}`")
        self.assertFalse(marker.exists())

    def test_profile_files_are_not_modified(self):
        paths = [self.write_profile(p, f"synthetic-{p}-key") for p in ("dev", "prod")]
        before = [p.read_bytes() for p in paths]
        probe.load_config(self.root, "dev", {})
        probe.load_config(self.root, "prod", {})
        self.assertEqual(before, [p.read_bytes() for p in paths])

    def test_prod_can_receive_secret_from_process_without_prod_file(self):
        config = probe.load_config(self.root, "prod", {
            "BIZINFO_SERVICE_KEY": SYNTHETIC_KEY, "BIZINFO_DATA_TYPE": "json",
            "BIZINFO_API_BASE_URL": probe.contract()["request"]["endpoint"],
        })
        self.assertEqual(config["key"], SYNTHETIC_KEY)
        self.assertEqual(config["profile"], "prod")
        self.assertFalse((self.root / ".env.prod").exists())


class BizinfoLocalProbeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.sample = FIXTURE.read_bytes()
        self.environment = {"BIZINFO_SERVICE_KEY": SYNTHETIC_KEY}

    def fake_success(self, url):
        params = parse_qs(urlsplit(url).query)
        self.assertEqual(params["serviceKey"], [SYNTHETIC_KEY])
        payload = json.loads(self.sample)
        body = payload["response"]["body"]
        body["pageNo"] = int(params["pageNo"][0])
        if "pblancId" in params:
            if params["pblancId"][0] == probe.contract()["probe"]["presumed_missing_id"]:
                payload["response"]["header"] = {"resultCode": "03", "resultMsg": "NODATA_ERROR"}
                payload["response"]["body"] = {"items": {}, "pageNo": 1, "numOfRows": 0, "totalCount": 0}
                return 200, json.dumps(payload).encode("utf-8")
            body["items"]["item"] = [item for item in body["items"]["item"]
                                    if item["pblancId"] == params["pblancId"][0]]
        return 200, json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def test_missing_credential_means_no_request_and_not_run(self):
        def forbidden_fetch(url):
            self.fail("network should not run")
        result = probe.run_probe(self.root, "dev", "missing-key", "all", {}, forbidden_fetch)
        self.assertEqual(result["execution"], "not_run")
        self.assertEqual(result["reason"], "credential_missing")
        self.assertEqual(result["observations"], [])
        self.assertEqual(result["analysis"]["recent_100_rule"], "unconfirmed")
        self.assertFalse((self.root / "data/raw").exists())

    def test_four_request_plan_records_http_pagination_ids_and_raw_checksums(self):
        urls = []
        def fetch(url):
            urls.append(url)
            return self.fake_success(url)
        result = probe.run_probe(self.root, "dev", "four-requests", "all", self.environment, fetch)
        self.assertEqual(len(urls), 4)
        self.assertEqual([item["outcome"] for item in result["observations"]],
                         ["SUCCESS", "SUCCESS", "SUCCESS", "EXPECTED_NO_DATA"])
        self.assertEqual(result["analysis"]["pagination"]["item_counts"], [10, 10])
        self.assertTrue(result["analysis"]["pagination"]["cross_page_duplicate_ids"])
        self.assertTrue(result["analysis"]["pagination"]["totalCount_consistent"])
        self.assertTrue(result["analysis"]["identifiers"][0]["single_exact_match"])
        self.assertTrue(result["analysis"]["identifiers"][1]["empty_observed"])
        self.assertEqual(result["analysis"]["recent_100_rule"], "unconfirmed")
        for item in result["observations"]:
            metadata = phase0.verify_snapshot(self.root / item["raw_snapshot"])
            self.assertIsNotNone(metadata["collected_at"])

    def test_report_and_stdout_never_contain_synthetic_key_or_auth_query(self):
        with patch.object(probe, "http_get", side_effect=self.fake_success):
            output, error = io.StringIO(), io.StringIO()
            with redirect_stdout(output), redirect_stderr(error):
                code = probe.main(["--profile", "dev", "--run-id", "safe-output"], self.root, self.environment)
        self.assertEqual(code, 0)
        report = (self.root / "harness/workspace/artifacts/bizinfo-probe-safe-output.json").read_text(encoding="utf-8")
        for text in (report, output.getvalue(), error.getvalue()):
            self.assertNotIn(SYNTHETIC_KEY, text)
            self.assertNotIn(quote(SYNTHETIC_KEY, safe=""), text)
            self.assertNotIn("serviceKey=", text)

    def test_profile_file_key_is_absent_from_mock_report_stdout_stderr_and_log(self):
        for profile in ("dev", "prod"):
            with self.subTest(profile=profile):
                path = self.root / f".env.{profile}"
                path.write_text(f"BIZINFO_SERVICE_KEY={SYNTHETIC_KEY}\n", encoding="utf-8")
                before = path.read_bytes()
                output, error = io.StringIO(), io.StringIO()
                with patch.object(probe, "http_get", side_effect=self.fake_success):
                    with redirect_stdout(output), redirect_stderr(error):
                        code = probe.main(["--profile", profile, "--run-id", f"file-{profile}"], self.root, {})
                self.assertEqual(code, 0)
                report = self.root / f"harness/workspace/artifacts/bizinfo-probe-file-{profile}.json"
                log = self.root / f"mock-{profile}.log"
                log.write_text(output.getvalue() + error.getvalue(), encoding="utf-8")
                for text in (report.read_text(encoding="utf-8"), log.read_text(encoding="utf-8")):
                    self.assertNotIn(SYNTHETIC_KEY, text)
                    self.assertNotIn(quote(SYNTHETIC_KEY, safe=""), text)
                    self.assertNotIn("serviceKey=", text)
                self.assertEqual(path.read_bytes(), before)

    def test_network_error_url_and_arbitrary_transport_message_are_not_logged(self):
        for exception in (URLError(f"https://example.invalid/?serviceKey={SYNTHETIC_KEY}"),
                          probe.ProbeError(SYNTHETIC_KEY), BadStatusLine(SYNTHETIC_KEY)):
            with self.subTest(exception=type(exception).__name__):
                def fetch(url):
                    raise exception
                config = probe.load_config(self.root, "dev", self.environment)
                item = probe.probe_one(config, "page1", {"dataType": "json", "pageNo": 1, "numOfRows": 10},
                                      "network-failure", self.root, fetch)
                self.assertEqual(item["status"], "failed")
                self.assertNotIn(SYNTHETIC_KEY, json.dumps(item))
                self.assertIsNone(item["raw_snapshot"])

    def test_credential_echo_refuses_raw_persistence_without_changing_original(self):
        variants = [SYNTHETIC_KEY, quote(SYNTHETIC_KEY, safe="")]
        variants.append("".join("\\u%04x" % ord(char) for char in SYNTHETIC_KEY))
        config = probe.load_config(self.root, "dev", self.environment)
        for echo in variants:
            with self.subTest(echo_type=len(echo)):
                raw = ('{"error":"' + echo + '"}').encode("utf-8")
                item = probe.probe_one(config, "page1", {"dataType": "json", "pageNo": 1, "numOfRows": 10},
                                      "echo-refused", self.root, lambda url: (403, raw))
                self.assertEqual(item["error"], "credential_echo_response_not_preserved")
                self.assertIsNone(item["raw_snapshot"])
                self.assertNotIn(SYNTHETIC_KEY, json.dumps(item))
        self.assertFalse((self.root / "data/raw").exists())

    def test_invalid_and_http_error_responses_are_preserved_as_failed_evidence(self):
        config = probe.load_config(self.root, "dev", self.environment)
        cases = [(200, b'{"wrong":"envelope"}', "invalid_response_envelope"),
                 (503, b"<gateway-error/>", "http_error")]
        for index, (status, raw, error) in enumerate(cases):
            item = probe.probe_one(config, "page1", {"dataType": "json", "pageNo": 1, "numOfRows": 10},
                                  f"failed-response-{index}", self.root, lambda url: (status, raw))
            self.assertEqual(item["status"], "failed")
            self.assertEqual(item["http_status"], status)
            self.assertEqual(item["error"], error)
            metadata = phase0.verify_snapshot(self.root / item["raw_snapshot"])
            saved = (self.root / item["raw_snapshot"]).parent / metadata["raw_path"]
            self.assertEqual(saved.read_bytes(), raw)

    def test_observed_no_data_shape_is_synthetic_negative_evidence_not_success(self):
        # Live 원문을 Fixture로 복사하지 않고 관찰된 빈 형태만 합성해 오류를 성공으로 오인하지 않게 한다.
        payload = {"response": {
            "header": {"resultCode": "03", "resultMsg": "NODATA_ERROR"},
            "body": {"items": {}, "numOfRows": 0, "pageNo": 1, "totalCount": 0},
        }}
        raw = json.dumps(payload).encode("utf-8")
        config = probe.load_config(self.root, "dev", self.environment)
        item = probe.probe_one(config, "presumed_missing_id",
                              {"dataType": "json", "pageNo": 1, "numOfRows": 10},
                              "synthetic-no-data", self.root, lambda url: (200, raw))
        self.assertEqual(item["http_status"], 200)
        self.assertEqual(item["resultCode"], "03")
        self.assertEqual(item["resultMsg"], "NODATA_ERROR")
        self.assertEqual(item["status"], "failed")
        self.assertEqual(item["error"], "api_error")
        self.assertIsNone(item["item_count"])
        metadata = phase0.verify_snapshot(self.root / item["raw_snapshot"])
        saved = (self.root / item["raw_snapshot"]).parent / metadata["raw_path"]
        self.assertEqual(saved.read_bytes(), raw)
        with self.assertRaisesRegex(probe.ProbeError, "api_error"):
            probe.validate_response(payload)

    def test_no_data_is_expected_only_for_explicit_negative_plan(self):
        payload = {"response": {"header": {"resultCode": "03", "resultMsg": "NODATA_ERROR"},
                                "body": {"items": {}, "pageNo": 1, "numOfRows": 0, "totalCount": 0}}}
        raw = json.dumps(payload).encode()
        config = probe.load_config(self.root, "dev", self.environment)
        for index, (name, negative, expected) in enumerate([
            ("page1", False, "API_ERROR"), ("known_id", False, "API_ERROR"),
            ("presumed_missing_id", False, "API_ERROR"), ("presumed_missing_id", True, "EXPECTED_NO_DATA"),
            ("known_id", True, "API_ERROR"),
        ]):
            params = {"dataType": "json", "pageNo": 1, "numOfRows": 10,
                      "pblancId": probe.contract()["probe"]["presumed_missing_id"]}
            item = probe.probe_one(config, name, params, f"negative-{index}", self.root, lambda url: (200, raw), negative)
            self.assertEqual(item["outcome"], expected)

    def test_malformed_no_data_and_non_200_cannot_be_expected_negative(self):
        payload = {"response": {"header": {"resultCode": "03", "resultMsg": "NODATA_ERROR"},
                                "body": {"items": {}, "pageNo": 1, "numOfRows": 0, "totalCount": 1}}}
        config = probe.load_config(self.root, "dev", self.environment)
        params = {"dataType": "json", "pageNo": 1, "numOfRows": 10,
                  "pblancId": probe.contract()["probe"]["presumed_missing_id"]}
        item = probe.probe_one(config, "presumed_missing_id", params, "bad-negative", self.root,
                              lambda url: (200, json.dumps(payload).encode()), True)
        self.assertEqual(item["outcome"], "CONTRACT_ERROR")
        payload["response"]["body"]["totalCount"] = 0
        item = probe.probe_one(config, "presumed_missing_id", params, "http-negative", self.root,
                              lambda url: (503, json.dumps(payload).encode()), True)
        self.assertEqual(item["outcome"], "TRANSPORT_ERROR")

    def test_unexpected_success_for_negative_probe_keeps_exit_one(self):
        def fetch(url):
            params = parse_qs(urlsplit(url).query)
            if params.get("pblancId") == [probe.contract()["probe"]["presumed_missing_id"]]:
                payload = json.loads(self.sample)
                payload["response"]["body"]["items"]["item"] = []
                payload["response"]["body"]["totalCount"] = 0
                return 200, json.dumps(payload).encode()
            return self.fake_success(url)
        with patch.object(probe, "http_get", side_effect=fetch):
            with redirect_stdout(io.StringIO()):
                code = probe.main(["--profile", "dev", "--run-id", "unexpected-negative"], self.root, self.environment)
        self.assertEqual(code, 1)

    def test_pagination_echo_mismatch_is_not_reported_as_normal_response(self):
        config = probe.load_config(self.root, "dev", self.environment)
        item = probe.probe_one(config, "page2", {"dataType": "json", "pageNo": 2, "numOfRows": 10},
                              "wrong-page", self.root, lambda url: (200, self.sample))
        self.assertEqual(item["error"], "pagination_echo_mismatch")
        self.assertEqual(item["status"], "failed")

    def test_repeat_run_fails_before_network_and_preserves_existing_evidence(self):
        probe.run_probe(self.root, "dev", "unique-run", "pages", self.environment, self.fake_success)
        path = self.root / "harness/workspace/artifacts/bizinfo-probe-unique-run.json"
        before = path.read_bytes()
        with self.assertRaisesRegex(probe.ProbeError, "output_exists"):
            probe.run_probe(self.root, "dev", "unique-run", "pages", self.environment,
                            lambda url: self.fail("repeated network call"))
        self.assertEqual(path.read_bytes(), before)

    def test_partial_previous_raw_run_is_detected_before_any_request(self):
        path = self.root / "data/raw/partial-page2"
        path.mkdir(parents=True)
        with self.assertRaisesRegex(probe.ProbeError, "raw_output_exists"):
            probe.run_probe(self.root, "dev", "partial", "pages", self.environment,
                            lambda url: self.fail("network must not run"))

    def test_env_is_read_without_shell_execution_and_environment_takes_precedence(self):
        path = self.root / ".env.dev"
        path.write_text("BIZINFO_SERVICE_KEY='synthetic-file-key'\nBIZINFO_DATA_TYPE=json\n", encoding="utf-8")
        self.assertEqual(probe.load_config(self.root, "dev", {})["key"], "synthetic-file-key")
        self.assertEqual(probe.load_config(self.root, "dev", self.environment)["key"], SYNTHETIC_KEY)
        encoded = {"BIZINFO_SERVICE_KEY": quote(SYNTHETIC_KEY, safe="")}
        self.assertEqual(probe.load_config(self.root, "dev", encoded)["key"], SYNTHETIC_KEY)
        with self.assertRaises(probe.ProbeError):
            probe.load_config(self.root, "dev", {"BIZINFO_API_BASE_URL": "https://example.invalid"})

    def test_redirect_handler_never_forwards_credential(self):
        self.assertIsNone(probe.NoRedirect().redirect_request(None, None, 302, None, None, "https://example.invalid"))
        error = HTTPError("https://example.invalid/?serviceKey=synthetic", 302, "redirect", {}, io.BytesIO(b"{}"))
        with patch.object(probe, "build_opener") as build:
            build.return_value.open.side_effect = error
            status, raw = probe.http_get("https://example.invalid")
        self.assertEqual(status, 302)
        self.assertEqual(raw, b"{}")

    def test_known_and_presumed_missing_identifier_are_observations_not_guarantees(self):
        result = probe.run_probe(self.root, "dev", "identifier-only", "identifier", self.environment, self.fake_success)
        self.assertEqual(len(result["observations"]), 2)
        self.assertEqual(result["analysis"]["pagination"]["status"], "unconfirmed")
        self.assertTrue(result["analysis"]["identifiers"][0]["single_exact_match"])
        self.assertIsNone(result["analysis"]["identifiers"][1]["all_returned_ids_match"])


if __name__ == "__main__":
    unittest.main()
