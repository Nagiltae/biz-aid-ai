import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]

sys.path.insert(
    0,
    str(ROOT / "data-pipeline/src"),
)


from biz_aid_pipeline.storage.s3_migration import (
    LocalDocument,
    S3MigrationError,
    S3MigrationService,
)


class FakeStore:
    region = "ap-southeast-2"
    bucket = "test-bucket"
    prefix = "biz-aid/documents"

    def __init__(self):
        self.objects = {}
        self.put_calls = 0

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
        self.put_calls += 1
        raise AssertionError("metadata link must not call PutObject")

    def verify(
            self,
            sha256_hex,
            byte_size,
    ):
        raw = self.objects.get(
            self.object_key(
                sha256_hex
            )
        )

        return (
                raw is not None
                and len(raw)
                == byte_size
                and hashlib.sha256(
            raw
        ).hexdigest()
                == sha256_hex
        )


def build_service(
        root,
        documents,
):
    service = object.__new__(
        S3MigrationService
    )

    service.root = root

    service.store = FakeStore()

    service.db_config = (
        SimpleNamespace()
    )

    service.s3_config = (
        SimpleNamespace(
            region="ap-southeast-2",
            bucket="test-bucket",
        )
    )

    service.engine = None

    service._load_documents = (
        lambda: documents
    )

    for document in documents:
        local_file = service._resolve_local_file(document.storage_path)
        if local_file.is_file():
            service.store.objects[
                service.store.object_key(document.sha256)
            ] = local_file.read_bytes()

    service.database_updates = []

    def update_database(
            migrated,
            expected_relation_count,
    ):
        service.database_updates.append(
            (
                list(migrated),
                expected_relation_count,
            )
        )

    service._update_database = (
        update_database
    )

    return service


class S3MigrationTests(
    unittest.TestCase
):
    def test_partial_migration_never_updates_database(
            self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(
                directory
            ).resolve()

            raw = b"document"

            digest = hashlib.sha256(
                raw
            ).hexdigest()

            relative = (
                    Path("data")
                    / "downloaded"
                    / "blobs"
                    / digest[:2]
                    / f"{digest}.bin"
            )

            file_path = (
                    root / relative
            )

            file_path.parent.mkdir(
                parents=True
            )

            file_path.write_bytes(
                raw
            )

            document = LocalDocument(
                sha256=digest,
                byte_size=len(raw),
                storage_path=str(
                    relative
                ),
                relation_count=2,
            )

            service = build_service(
                root,
                [document],
            )

            result = service.migrate(
                limit=1,
                write_db=False,
            )

            self.assertEqual(
                result.unique_binary_count,
                1,
            )

            self.assertEqual(
                result.relation_count,
                2,
            )

            self.assertEqual(
                result.migrated_binary_count,
                1,
            )

            self.assertFalse(
                result.db_updated
            )

            self.assertEqual(service.store.put_calls, 0)

            self.assertEqual(
                service.database_updates,
                [],
            )

    def test_partial_migration_cannot_write_database(
            self,
    ):
        service = build_service(
            ROOT,
            [],
        )

        with self.assertRaises(
                S3MigrationError
        ):
            service.migrate(
                limit=1,
                write_db=True,
            )

    def test_full_migration_updates_database_only_after_s3_verification(
            self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(
                directory
            ).resolve()

            documents = []

            for index in range(2):
                raw = (
                    f"document-{index}"
                ).encode()

                digest = hashlib.sha256(
                    raw
                ).hexdigest()

                relative = (
                        Path("data")
                        / "downloaded"
                        / "blobs"
                        / digest[:2]
                        / f"{digest}.bin"
                )

                path = (
                        root / relative
                )

                path.parent.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                path.write_bytes(
                    raw
                )

                documents.append(
                    LocalDocument(
                        sha256=digest,
                        byte_size=len(raw),
                        storage_path=str(
                            relative
                        ),
                        relation_count=(
                            2
                            if index == 0
                            else 1
                        ),
                    )
                )

            service = build_service(
                root,
                documents,
            )

            result = service.migrate(
                write_db=True,
            )

            self.assertTrue(
                result.db_updated
            )

            self.assertEqual(
                result.unique_binary_count,
                2,
            )

            self.assertEqual(
                result.relation_count,
                3,
            )

            self.assertEqual(
                len(
                    service.store.objects
                ),
                2,
            )

            self.assertEqual(service.store.put_calls, 0)

            self.assertEqual(
                len(
                    service.database_updates
                ),
                1,
            )

            migrated, relation_count = (
                service.database_updates[
                    0
                ]
            )

            self.assertEqual(
                len(migrated),
                2,
            )

            self.assertEqual(
                relation_count,
                3,
            )

    def test_missing_s3_object_fails_without_upload(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            raw = b"document"
            digest = hashlib.sha256(raw).hexdigest()
            relative = Path("data/downloaded/blobs") / f"{digest}.bin"
            path = root / relative
            path.parent.mkdir(parents=True)
            path.write_bytes(raw)
            document = LocalDocument(digest, len(raw), str(relative), 1)
            service = build_service(root, [document])
            service.store.objects.clear()

            with self.assertRaises(S3MigrationError):
                service.migrate(write_db=True)

            self.assertEqual(service.store.put_calls, 0)
            self.assertEqual(service.database_updates, [])

    def test_storage_path_escape_is_rejected(
            self,
    ):
        service = build_service(
            ROOT,
            [],
        )

        with self.assertRaises(
                S3MigrationError
        ):
            service._resolve_local_file(
                "../../etc/passwd"
            )


if __name__ == "__main__":
    unittest.main()
