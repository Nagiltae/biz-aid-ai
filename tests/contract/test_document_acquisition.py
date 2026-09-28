import hashlib
import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock
from urllib.error import URLError

ROOT = Path(__file__).resolve().parents[2]

sys.path.insert(
    0,
    str(ROOT / "data-pipeline/src"),
)
sys.path.insert(
    0,
    str(ROOT / "tests/contract"),
)

from test_phase0_document_download import (
    PDF,
    Response,
    hwp_fixture,
    zip_fixture,
)

from biz_aid_pipeline.config.settings import PipelineError
from biz_aid_pipeline.documents.client import public_url, transfer
from biz_aid_pipeline.documents.formats import actual_format
from biz_aid_pipeline.documents.models import candidates
from biz_aid_pipeline.documents.service import (
    store_acquired_body,
    validate_report,
    verify_stored,
)


KEY = "synthetic-document-secret+/="

URL = (
    "https://www.bizinfo.go.kr/"
    "cmm/fms/getImageFile.do?"
    "atchFileId=FILE_SYNTHETIC&fileSn=0"
)

SPEC = json.loads(
    (
            ROOT
            / "contracts/schemas/document-acquisition.contract.json"
    ).read_bytes()
)


class FakeS3Store:
    """
    실제 AWS를 호출하지 않고
    S3DocumentStore의 service 경계를 테스트한다.
    """

    region = "ap-southeast-2"
    bucket = "test-biz-aid-bucket"
    prefix = "biz-aid/documents"

    def __init__(self):
        self.objects = {}

    def object_key(
            self,
            sha256_hex,
    ):
        return (
            f"{self.prefix}/sha256/"
            f"{sha256_hex[:2]}/"
            f"{sha256_hex[2:4]}/"
            f"{sha256_hex}"
        )

    def put(
            self,
            file_path,
            sha256_hex,
            byte_size,
    ):
        raw = Path(file_path).read_bytes()

        if len(raw) != byte_size:
            raise ValueError(
                "fake_s3_size_mismatch"
            )

        actual_sha256 = hashlib.sha256(
            raw
        ).hexdigest()

        if actual_sha256 != sha256_hex:
            raise ValueError(
                "fake_s3_sha_mismatch"
            )

        key = self.object_key(
            sha256_hex
        )

        existing = self.objects.get(
            key
        )

        if (
                existing is not None
                and existing != raw
        ):
            raise RuntimeError(
                "fake_s3_overwrite_refused"
            )

        self.objects.setdefault(
            key,
            raw,
        )

        return key

    def exists(
            self,
            sha256_hex,
    ):
        return (
                self.object_key(sha256_hex)
                in self.objects
        )

    def verify(
            self,
            sha256_hex,
            byte_size,
    ):
        key = self.object_key(
            sha256_hex
        )

        raw = self.objects.get(
            key
        )

        if raw is None:
            return False

        return (
                len(raw) == byte_size
                and hashlib.sha256(
            raw
        ).hexdigest()
                == sha256_hex
        )

    def read(
            self,
            sha256_hex,
            byte_size,
            max_bytes=100 * 1024 * 1024,
    ):
        key = self.object_key(
            sha256_hex
        )

        raw = self.objects.get(
            key
        )

        if raw is None:
            raise RuntimeError(
                "fake_s3_object_missing"
            )

        if len(raw) > max_bytes:
            raise RuntimeError(
                "fake_s3_read_limit"
            )

        if not self.verify(
                sha256_hex,
                byte_size,
        ):
            raise RuntimeError(
                "fake_s3_integrity_failure"
            )

        return raw


class DocumentAcquisitionContractTests(
    unittest.TestCase
):
    def test_candidate_extraction_preserves_source_provenance(
            self,
    ):
        rows = candidates(
            "PBLN_TEST",
            URL,
            "공고.pdf",
            URL + "1@" + URL + "2",
            "첨부.hwp@서식.hwpx",
            )

        self.assertEqual(
            [
                row.source_role
                for row in rows
            ],
            [
                "PRINT_CANDIDATE",
                "ATTACHMENT_CANDIDATE",
                "ATTACHMENT_CANDIDATE",
            ],
        )

        self.assertEqual(
            [
                row.source_url_field
                for row in rows
            ],
            [
                "printFlpthNm",
                "flpthNm",
                "flpthNm",
            ],
        )

        self.assertEqual(
            [
                row.source_token_index
                for row in rows
            ],
            [0, 0, 1],
        )

        self.assertEqual(
            [
                row.declared_extension
                for row in rows
            ],
            ["PDF", "HWP", "HWPX"],
        )

        self.assertEqual(
            len(
                {
                    row.candidate_key
                    for row in rows
                }
            ),
            3,
        )

    def test_unpaired_filename_is_preserved_as_observation(
            self,
    ):
        rows = candidates(
            "PBLN_TEST",
            None,
            None,
            URL + "1@" + URL + "2",
            "한개.pdf",
            )

        self.assertEqual(
            [
                row.pairing_status
                for row in rows
            ],
            [
                "UNPAIRED",
                "UNPAIRED",
            ],
        )

        self.assertIsNone(
            rows[1].original_filename
        )

    def test_duplicate_url_keeps_distinct_relations(
            self,
    ):
        first = candidates(
            "PBLN_A",
            URL,
            "a.pdf",
            None,
            None,
        )[0]

        second = candidates(
            "PBLN_B",
            URL,
            "b.pdf",
            None,
            None,
        )[0]

        self.assertEqual(
            first.source_url_sha256,
            second.source_url_sha256,
        )

        self.assertNotEqual(
            first.candidate_key,
            second.candidate_key,
        )

    def test_pdf_hwp_hwpx_and_unknown_signatures(
            self,
    ):
        self.assertEqual(
            actual_format(PDF),
            "PDF",
        )

        self.assertEqual(
            actual_format(
                hwp_fixture()
            ),
            "HWP",
        )

        self.assertEqual(
            actual_format(
                zip_fixture("HWPX")
            ),
            "HWPX",
        )

        self.assertEqual(
            actual_format(
                b"unknown-safe-binary"
            ),
            "UNKNOWN",
        )

    def call(
            self,
            raw=PDF,
            status=200,
            headers=None,
            fetch=None,
    ):
        response = (
            lambda request, timeout:
            Response(
                raw,
                status,
                headers,
            )
        )

        return transfer(
            URL,
            KEY,
            SPEC,
            fetch or response,
            )

    def test_unknown_is_acquired_and_html_is_invalid_response(
            self,
    ):
        unknown, raw = self.call(
            b"unknown-safe-binary"
        )

        self.assertIsNone(
            unknown["failure_category"]
        )

        self.assertEqual(
            unknown["detected_format"],
            "UNKNOWN",
        )

        self.assertEqual(
            raw,
            b"unknown-safe-binary",
        )

        html, raw = self.call(
            b"<!doctype html><title>error</title>"
        )

        self.assertEqual(
            html["failure_category"],
            "INVALID_RESPONSE",
        )

        self.assertTrue(
            html["invalid_response"]
        )

        self.assertIsNotNone(raw)

    def test_http_and_network_failure_are_explicit_without_retry(
            self,
    ):
        http, raw = self.call(
            b"not found",
            404,
        )

        self.assertEqual(
            http["failure_category"],
            "HTTP_ERROR",
        )

        self.assertEqual(
            raw,
            b"not found",
        )

        fetch = Mock(
            side_effect=URLError(KEY)
        )

        network, raw = self.call(
            fetch=fetch
        )

        self.assertEqual(
            network["failure_category"],
            "TRANSPORT_ERROR",
        )

        self.assertIsNone(raw)

        self.assertEqual(
            fetch.call_count,
            1,
        )

    def test_redirect_limit_and_secret_never_followed(
            self,
    ):
        fetch = Mock(
            return_value=Response(
                status=302,
                headers={
                    "Location":
                        URL
                        + "&serviceKey="
                        + KEY
                },
            )
        )

        result, raw = self.call(
            fetch=fetch
        )

        self.assertEqual(
            result["failure_category"],
            "REDIRECT_ERROR",
        )

        self.assertIsNone(raw)

        self.assertEqual(
            fetch.call_count,
            1,
        )

        self.assertNotIn(
            KEY,
            json.dumps(result),
        )

    def test_file_size_limit_uses_streamed_bytes(
            self,
    ):
        spec = dict(
            SPEC,
            max_file_bytes=20,
        )

        result, raw = transfer(
            URL,
            KEY,
            spec,
            lambda request, timeout:
            Response(b"x" * 200),
        )

        self.assertEqual(
            result["failure_category"],
            "SIZE_LIMIT_EXCEEDED",
        )

        self.assertEqual(
            len(raw),
            20,
        )

    def test_s3_content_address_dedupe_and_integrity(
            self,
    ):
        store = FakeS3Store()

        first = store_acquired_body(
            PDF,
            store,
        )

        second = store_acquired_body(
            PDF,
            store,
        )

        self.assertEqual(
            first["s3_object_key"],
            second["s3_object_key"],
        )

        self.assertEqual(
            first["storage_path"],
            first["s3_object_key"],
        )

        # 같은 content를 두 번 저장해도
        # S3 object는 하나만 존재한다.
        self.assertEqual(
            len(store.objects),
            1,
        )

        row = {
            "download_status": "ACQUIRED",
            "byte_size": len(PDF),
            "content_sha256":
                hashlib.sha256(
                    PDF
                ).hexdigest(),
            "detected_format": "PDF",
            "storage_path":
                first["storage_path"],
            "s3_region":
                first["s3_region"],
            "s3_bucket_name":
                first["s3_bucket_name"],
            "s3_object_key":
                first["s3_object_key"],
            "s3_verified_at":
                first["s3_verified_at"],
        }

        self.assertTrue(
            verify_stored(
                ROOT,
                row,
                store,
            )
        )

        # 실제 저장 byte가 변조되면
        # Quality Gate가 실패해야 한다.
        store.objects[
            first["s3_object_key"]
        ] = b"tampered"

        self.assertFalse(
            verify_stored(
                ROOT,
                row,
                store,
            )
        )

    def test_s3_metadata_must_be_complete(
            self,
    ):
        store = FakeS3Store()

        digest = hashlib.sha256(
            PDF
        ).hexdigest()

        row = {
            "download_status": "ACQUIRED",
            "byte_size": len(PDF),
            "content_sha256": digest,
            "detected_format": "PDF",
            "storage_path":
                store.object_key(digest),
            "s3_region":
                store.region,
            "s3_bucket_name":
                store.bucket,
            "s3_object_key":
                None,
            "s3_verified_at":
                None,
        }

        self.assertFalse(
            verify_stored(
                ROOT,
                row,
                store,
            )
        )

    def test_url_policy_rejects_authentication_and_other_hosts(
            self,
    ):
        self.assertTrue(
            public_url(
                URL,
                SPEC,
            )
        )

        self.assertFalse(
            public_url(
                URL
                + "&serviceKey=x",
                SPEC,
                )
        )

        self.assertFalse(
            public_url(
                "https://evil.invalid/file.pdf",
                SPEC,
            )
        )

    def test_quality_contract_rejects_false_pass(
            self,
    ):
        report = {
            name: 0
            for name in (
                "support_program_count",
                "programs_with_document_candidate",
                "programs_without_document_candidate",
                "total_candidate_relations",
                "unique_source_url_count",
                "duplicate_url_count",
                "attempted_downloads",
                "http_request_count",
                "reused_relation_count",
                "success_count",
                "failed_count",
                "pdf_count",
                "hwp_count",
                "hwpx_count",
                "other_unknown_count",
                "duplicate_content_sha_count",
                "invalid_response_count",
                "format_mismatch_count",
                "total_downloaded_bytes",
                "persisted_metadata_count",
                "integrity_failure_count",
            )
        }

        report.update(
            run_id="r",
            phase="phase2-document-acquisition",
            profile="dev",
            status="PASS",
            source_snapshot_sha256=(
                hashlib.sha256(
                    b""
                ).hexdigest()
            ),
            source_snapshot_unchanged=True,
            format_counts={},
            failure_candidates=[],
            failure_category_counts={},
            http_status_distribution={},
            content_type_distribution={},
            started_at="x",
            finished_at="x",
            elapsed_seconds=0,
            automatic_retries=0,
            parser_scope=False,
            gate_rule=SPEC["gate_pass"],
        )

        with self.assertRaises(
                PipelineError
        ):
            validate_report(
                ROOT,
                report,
            )

        valid = dict(
            report,
            support_program_count=1,
            programs_with_document_candidate=1,
            total_candidate_relations=1,
            unique_source_url_count=1,
            success_count=1,
            persisted_metadata_count=1,
            pdf_count=1,
            total_downloaded_bytes=len(PDF),
            format_counts={"PDF": 1},
        )

        validate_report(
            ROOT,
            valid,
        )

        with self.assertRaises(
                PipelineError
        ):
            validate_report(
                ROOT,
                dict(
                    valid,
                    failed_count=1,
                ),
            )


if __name__ == "__main__":
    unittest.main()
