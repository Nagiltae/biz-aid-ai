import base64
import hashlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

from botocore.exceptions import ClientError


ROOT = Path(__file__).resolve().parents[2]

sys.path.insert(
    0,
    str(ROOT / "data-pipeline/src"),
)

from biz_aid_pipeline.storage.s3_document_store import (
    S3DocumentStore,
)
from biz_aid_pipeline.config.settings import PipelineError, S3Config


class FakeS3Client:
    def __init__(self):
        self.objects = {}
        self.put_calls = 0

    @staticmethod
    def _missing(
            operation,
    ):
        raise ClientError(
            {
                "Error": {
                    "Code": "404",
                    "Message":
                        "Not Found",
                },
                "ResponseMetadata": {
                    "HTTPStatusCode": 404,
                },
            },
            operation,
        )

    def head_object(
            self,
            Bucket,
            Key,
            ChecksumMode=None,
    ):
        item = self.objects.get(
            (Bucket, Key)
        )

        if item is None:
            self._missing(
                "HeadObject"
            )

        response = {
            "ContentLength":
                len(item["raw"]),
        }

        if ChecksumMode == "ENABLED":
            response[
                "ChecksumSHA256"
            ] = item["checksum"]

        return response

    def put_object(
            self,
            Bucket,
            Key,
            Body,
            ContentLength,
            ContentType,
            ChecksumSHA256,
            IfNoneMatch=None,
    ):
        identity = (
            Bucket,
            Key,
        )

        if (
                IfNoneMatch == "*"
                and identity
                in self.objects
        ):
            raise ClientError(
                {
                    "Error": {
                        "Code":
                            "PreconditionFailed",
                    },
                    "ResponseMetadata": {
                        "HTTPStatusCode":
                            412,
                    },
                },
                "PutObject",
            )

        # 파일 객체(put)와 메모리 byte(put_bytes)를 모두 받는다. boto3도 두 형태를 같은 PUT으로 보낸다.
        raw = Body.read() if hasattr(Body, "read") else bytes(Body)

        if len(raw) != ContentLength:
            raise AssertionError(
                "ContentLength mismatch"
            )

        self.objects[
            identity
        ] = {
            "raw": raw,
            "checksum":
                ChecksumSHA256,
            "content_type":
                ContentType,
        }

        self.put_calls += 1

        return {}

    def get_object(
            self,
            Bucket,
            Key,
            ChecksumMode=None,
    ):
        item = self.objects.get(
            (Bucket, Key)
        )

        if item is None:
            self._missing(
                "GetObject"
            )

        response = {
            "Body":
                io.BytesIO(
                    item["raw"]
                ),
        }

        if ChecksumMode == "ENABLED":
            response[
                "ChecksumSHA256"
            ] = item["checksum"]

        return response


class S3DocumentStoreTests(
    unittest.TestCase
):
    def setUp(self):
        self.client = FakeS3Client()

        self.store = S3DocumentStore(
            bucket="test-bucket",
            region="ap-southeast-2",
            prefix="biz-aid/documents",
            client=self.client,
        )

    def test_put_bytes_uses_same_key_and_never_overwrites(self):
        # 압축 내부 파일은 디스크에 풀지 않고 메모리 byte를 원본과 같은 content key로 저장한다.
        raw = b"biz-aid-archive-member"
        digest = hashlib.sha256(raw).hexdigest()
        key = self.store.put_bytes(raw, digest)
        self.assertEqual(key, self.store.object_key(digest))
        self.assertEqual(self.store.put_bytes(raw, digest), key)
        self.assertEqual(self.client.put_calls, 1)
        self.assertEqual(self.store.read_key(key, digest, len(raw)), raw)
        # 이미 있는 object가 다른 byte면 덮어쓰지 않고 실패한다.
        self.client.objects[("test-bucket", key)]["raw"] = b"tampered-member"
        with self.assertRaises(RuntimeError):
            self.store.put_bytes(raw, digest)
        self.assertEqual(self.client.put_calls, 1)
        with self.assertRaises(ValueError):
            self.store.put_bytes(b"other", digest)
        with self.assertRaises(ValueError):
            self.store.put_bytes(b"", hashlib.sha256(b"").hexdigest())

    def test_put_verify_read_and_reuse(
            self,
    ):
        raw = b"biz-aid-test-document"

        digest = hashlib.sha256(
            raw
        ).hexdigest()

        with tempfile.TemporaryDirectory() as directory:
            path = (
                    Path(directory)
                    / "document.bin"
            )

            path.write_bytes(raw)

            first_key = self.store.put(
                path,
                digest,
                len(raw),
            )

            second_key = self.store.put(
                path,
                digest,
                len(raw),
            )

        self.assertEqual(
            first_key,
            second_key,
        )

        # 두 번째 put은 기존 object를 검증 후
        # 재사용하므로 실제 PUT은 한 번뿐이다.
        self.assertEqual(
            self.client.put_calls,
            1,
        )

        self.assertTrue(
            self.store.verify(
                digest,
                len(raw),
            )
        )

        self.assertEqual(
            self.store.read(
                digest,
                len(raw),
            ),
            raw,
        )

    def test_object_key_uses_content_sha(
            self,
    ):
        digest = (
                "abcdef"
                + "0" * 58
        )

        self.assertEqual(
            self.store.object_key(digest),
            "biz-aid/documents/sha256/ab/cd/" + digest,
        )

    def test_s3_config_is_fixed_to_approved_dev_storage(self):
        environ = {
            "AWS_REGION": "ap-southeast-2",
            "AWS_S3_BUCKET": "amazon-s3-biz-aid-bucket-695694684371-ap-southeast-2-an",
            "AWS_S3_PREFIX": "biz-aid/documents",
        }
        config = S3Config.load(ROOT, "dev", environ)
        self.assertEqual(config.region, "ap-southeast-2")

        environ["AWS_S3_BUCKET"] = "wrong-bucket"
        with self.assertRaises(PipelineError):
            S3Config.load(ROOT, "dev", environ)

    def test_prod_s3_is_rejected_before_configuration_read(self):
        with self.assertRaises(PipelineError):
            S3Config.load(ROOT, "prod", {})

    def test_wrong_local_sha_is_rejected(
            self,
    ):
        raw = b"original"

        wrong_digest = hashlib.sha256(
            b"different"
        ).hexdigest()

        with tempfile.TemporaryDirectory() as directory:
            path = (
                    Path(directory)
                    / "document.bin"
            )

            path.write_bytes(raw)

            with self.assertRaises(
                    ValueError
            ):
                self.store.put(
                    path,
                    wrong_digest,
                    len(raw),
                )

        self.assertEqual(
            self.client.put_calls,
            0,
        )

    def test_existing_object_with_wrong_checksum_is_not_reused(
            self,
    ):
        raw = b"original"

        digest = hashlib.sha256(
            raw
        ).hexdigest()

        with tempfile.TemporaryDirectory() as directory:
            path = (
                    Path(directory)
                    / "document.bin"
            )

            path.write_bytes(raw)

            key = self.store.put(
                path,
                digest,
                len(raw),
            )

            tampered = b"tampered"

            self.client.objects[
                (
                    self.store.bucket,
                    key,
                )
            ] = {
                "raw": tampered,
                "checksum":
                    base64.b64encode(
                        hashlib.sha256(
                            tampered
                        ).digest()
                    ).decode(
                        "ascii"
                    ),
                "content_type":
                    "application/octet-stream",
            }

            with self.assertRaises(
                    RuntimeError
            ):
                self.store.put(
                    path,
                    digest,
                    len(raw),
                )

    def test_read_recalculates_actual_sha(
            self,
    ):
        raw = b"original"

        digest = hashlib.sha256(
            raw
        ).hexdigest()

        with tempfile.TemporaryDirectory() as directory:
            path = (
                    Path(directory)
                    / "document.bin"
            )

            path.write_bytes(raw)

            key = self.store.put(
                path,
                digest,
                len(raw),
            )

        # HEAD metadata만 정상인 것처럼 두고
        # 실제 body만 변조한다.
        item = self.client.objects[
            (
                self.store.bucket,
                key,
            )
        ]

        item["raw"] = b"x" * len(raw)

        # verify는 metadata만 검사하기 때문에
        # 여기서는 통과할 수 있다.
        self.assertTrue(
            self.store.verify(
                digest,
                len(raw),
            )
        )

        # 실제 GET readback에서는 byte SHA를
        # 다시 계산하므로 변조를 잡아낸다.
        with self.assertRaises(
                RuntimeError
        ):
            self.store.read(
                digest,
                len(raw),
            )


if __name__ == "__main__":
    unittest.main()
