import copy
import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("phase0", ROOT / "scripts/phase0.py")
phase0 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(phase0)


class ReportContractTests(unittest.TestCase):
    def setUp(self):
        self.report = phase0.new_report("contract-test")

    def test_initial_report_is_unmeasured_and_pending(self):
        phase0.validate_report(self.report)
        self.assertEqual(self.report["gate"]["decision"], "pending")
        self.assertTrue(all(item["value"] is None for item in self.report["metrics"].values()))

    def test_missing_or_unknown_fields_are_rejected(self):
        for mutation in ("missing", "unknown"):
            with self.subTest(mutation=mutation):
                report = copy.deepcopy(self.report)
                if mutation == "missing":
                    del report["metrics"]["hwp_parse_success"]
                else:
                    report["guessed_api_field"] = True
                with self.assertRaises(ValueError):
                    phase0.validate_report(report)

    def test_unmeasured_metric_cannot_claim_zero_or_success(self):
        for value in (0, 1):
            with self.subTest(value=value):
                self.report["metrics"]["api_collection_rate"]["value"] = value
                with self.assertRaises(ValueError):
                    phase0.validate_report(self.report)

    def measured_rate(self):
        metric = self.report["metrics"]["api_collection_rate"]
        metric.update(status="measured", value=0.99, numerator=99, denominator=100, evidence=["data/raw/run/metadata.json"])
        return metric

    def test_rate_requires_consistent_counts_and_evidence(self):
        self.measured_rate()
        phase0.validate_report(self.report)
        for changes in (
            {"value": 1},
            {"denominator": 0},
            {"numerator": 101},
            {"numerator": True},
            {"evidence": []},
            {"value": float("nan")},
        ):
            with self.subTest(changes=changes):
                report = copy.deepcopy(self.report)
                report["metrics"]["api_collection_rate"].update(changes)
                with self.assertRaises(ValueError):
                    phase0.validate_report(report)

    def test_count_distribution_and_qualitative_types(self):
        for name, invalid_value in (
            ("pblanc_id_duplicates", True),
            ("file_extensions", []),
            ("rag_value", 1),
            ("average_pages", -1),
        ):
            with self.subTest(name=name):
                report = copy.deepcopy(self.report)
                report["metrics"][name].update(status="measured", value=invalid_value, evidence=["reference"])
                with self.assertRaises(ValueError):
                    phase0.validate_report(report)

    def test_distribution_rejects_impossible_null_rates_and_fractional_file_counts(self):
        for name, invalid_value in (("major_field_null_rates", {"field": 1.5}), ("file_extensions", {"pdf": 1.5})):
            with self.subTest(name=name):
                report = copy.deepcopy(self.report)
                report["metrics"][name].update(status="measured", value=invalid_value, evidence=["reference"])
                with self.assertRaises(ValueError):
                    phase0.validate_report(report)

    def test_final_gate_cannot_be_claimed_in_preparation(self):
        for decision in ("go", "drop"):
            with self.subTest(decision=decision):
                self.report["gate"]["decision"] = decision
                self.report["gate"]["reviewer"] = "self"
                with self.assertRaises(ValueError):
                    phase0.validate_report(self.report)

    def test_timestamp_requires_timezone(self):
        self.report["created_at"] = "2026-09-27T12:00:00"
        with self.assertRaises(ValueError):
            phase0.validate_report(self.report)

    def test_design_sample_target_cannot_be_silently_lowered(self):
        self.report["sample"]["target_count"] = 10
        with self.assertRaises(ValueError):
            phase0.validate_report(self.report)


class SnapshotContractTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.input = self.directory / "input.json"
        self.raw = b'{ "synthetic": true, "unknown": null }\n'
        self.input.write_bytes(self.raw)
        self.metadata_path = phase0.snapshot(self.input, self.directory / "raw", "run-1", "application/json")

    def test_preserves_unknown_fields_and_exact_bytes(self):
        metadata = phase0.verify_snapshot(self.metadata_path)
        self.assertEqual((self.metadata_path.parent / metadata["raw_path"]).read_bytes(), self.raw)
        self.assertEqual(metadata["sha256"], hashlib.sha256(self.raw).hexdigest())

    def test_same_run_cannot_overwrite_existing_source(self):
        self.input.write_text('{"changed": true}\n', encoding="utf-8")
        with self.assertRaises(FileExistsError):
            phase0.snapshot(self.input, self.directory / "raw", "run-1", "application/json")
        phase0.verify_snapshot(self.metadata_path)

    def test_changed_source_is_detected(self):
        (self.metadata_path.parent / "response.json").write_bytes(b"{}")
        with self.assertRaises(ValueError):
            phase0.verify_snapshot(self.metadata_path)

    def test_path_traversal_and_symlink_are_rejected(self):
        metadata = phase0.read_json(self.metadata_path)
        metadata["raw_path"] = "../../input.json"
        with self.assertRaises(ValueError):
            phase0.validate_metadata(metadata)
        original = self.metadata_path.parent / "response.json"
        original.unlink()
        original.symlink_to(self.input)
        with self.assertRaises(ValueError):
            phase0.verify_snapshot(self.metadata_path)

    def test_bad_run_id_and_empty_payload_do_not_create_snapshot(self):
        with self.assertRaises(ValueError):
            phase0.snapshot(self.input, self.directory / "raw", "../escape", "application/json")
        self.input.write_bytes(b"")
        with self.assertRaises(ValueError):
            phase0.snapshot(self.input, self.directory / "raw", "empty", "application/json")
        self.assertFalse((self.directory / "raw/empty").exists())

    def test_xml_bytes_are_preserved_and_dtd_is_flagged_without_expansion(self):
        raw = b'<?xml version="1.0" encoding="UTF-8"?><sample><value>1</value></sample>\n'
        self.input.write_bytes(raw)
        path = phase0.snapshot(self.input, self.directory / "raw", "xml-run", "application/xml")
        phase0.verify_snapshot(path)
        self.assertEqual((path.parent / "response.xml").read_bytes(), raw)
        self.input.write_bytes(b'<!DOCTYPE a [<!ENTITY e "x">]><a>&e;</a>')
        saved = phase0.snapshot(self.input, self.directory / "raw", "xml-dtd", "application/xml")
        self.assertEqual(phase0.verify_snapshot(saved)["payload_syntax"], "invalid")

    def test_invalid_api_response_is_preserved_for_failure_analysis(self):
        for index, payload in enumerate((b'{"a": 1, "a": 2}', b'{"a": NaN}', b'{"a": Infinity}', b'not-json')):
            with self.subTest(payload=payload):
                self.input.write_bytes(payload)
                path = phase0.snapshot(self.input, self.directory / "raw", f"invalid-{index}", "application/json")
                self.assertEqual(phase0.verify_snapshot(path)["payload_syntax"], "invalid")
                self.assertEqual((path.parent / "response.json").read_bytes(), payload)

    def test_preservation_time_does_not_claim_unknown_collection_time(self):
        metadata = phase0.verify_snapshot(self.metadata_path)
        self.assertIsNone(metadata["collected_at"])
        phase0.timestamp(metadata["preserved_at"])
        path = phase0.snapshot(self.input, self.directory / "raw", "known-time", "application/json", "2026-09-27T09:00:00+09:00")
        self.assertEqual(phase0.verify_snapshot(path)["collected_at"], "2026-09-27T09:00:00+09:00")

    def test_metadata_type_and_unknown_field_are_rejected(self):
        metadata = phase0.read_json(self.metadata_path)
        for changes in ({"byte_count": True}, {"sha256": "not-a-hash"}, {"source": "unapproved"}, {"extra": "field"}):
            with self.subTest(changes=changes):
                changed = dict(metadata, **changes)
                with self.assertRaises(ValueError):
                    phase0.validate_metadata(changed)


if __name__ == "__main__":
    unittest.main()
