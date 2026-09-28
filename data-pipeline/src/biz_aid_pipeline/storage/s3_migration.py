from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import URL

from biz_aid_pipeline.config.settings import (
    DbConfig,
    S3Config,
)
from biz_aid_pipeline.storage.s3_document_store import (
    S3DocumentStore,
)


class S3MigrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class LocalDocument:
    sha256: str
    byte_size: int
    storage_path: str
    relation_count: int


@dataclass(frozen=True)
class MigratedDocument:
    sha256: str
    byte_size: int
    object_key: str


@dataclass(frozen=True)
class MigrationResult:
    unique_binary_count: int
    relation_count: int
    migrated_binary_count: int
    db_updated: bool


class S3MigrationService:
    def __init__(
            self,
            root: Path,
            db_config: DbConfig,
            s3_config: S3Config,
            store: S3DocumentStore,
    ) -> None:
        self.root = Path(root).resolve()
        self.db_config = db_config
        self.s3_config = s3_config
        self.store = store

        self.engine: Engine = create_engine(
            URL.create(
                "mysql+pymysql",
                username=db_config.user,
                password=db_config.password,
                host=db_config.host,
                port=db_config.port,
                database=db_config.database,
                query={
                    "charset": "utf8mb4",
                },
            ),
            hide_parameters=True,
            echo=False,
            pool_pre_ping=True,
        )

    def migrate(
            self,
            limit: int | None = None,
            write_db: bool = False,
    ) -> MigrationResult:
        if limit is not None and limit <= 0:
            raise S3MigrationError(
                "migration_limit_must_be_positive"
            )

        # 일부 object만 올린 상태에서 DB를 변경하면
        # relation 일부만 S3 metadata를 갖는 중간 상태가 생길 수 있다.
        if limit is not None and write_db:
            raise S3MigrationError(
                "partial_migration_cannot_update_database"
            )

        documents = self._load_documents()

        if not documents:
            raise S3MigrationError(
                "no_acquired_documents_to_migrate"
            )

        unique_binary_count = len(documents)

        relation_count = sum(
            document.relation_count
            for document in documents
        )

        selected = (
            documents[:limit]
            if limit is not None
            else documents
        )

        total_bytes = sum(
            document.byte_size
            for document in selected
        )

        migrated_bytes = 0
        migrated: list[MigratedDocument] = []

        started_at = time.monotonic()

        print(
            "S3 document migration starting",
            flush=True,
        )

        print(
            f"unique_binary_count="
            f"{unique_binary_count}",
            flush=True,
        )

        print(
            f"relation_count="
            f"{relation_count}",
            flush=True,
        )

        print(
            f"selected_binary_count="
            f"{len(selected)}",
            flush=True,
        )

        print(
            f"selected_bytes="
            f"{total_bytes}",
            flush=True,
        )

        for index, document in enumerate(
                selected,
                start=1,
        ):
            percent = (
                    index
                    / len(selected)
                    * 100
            )

            print(
                f"[{index}/{len(selected)}] "
                f"{percent:6.2f}% | "
                f"processing="
                f"{self._format_bytes(document.byte_size)} | "
                f"sha="
                f"{document.sha256[:12]}...",
                flush=True,
            )

            local_file = (
                self._resolve_local_file(
                    document.storage_path
                )
            )

            if (
                    not local_file.is_file()
                    or local_file.is_symlink()
            ):
                raise S3MigrationError(
                    "local_document_missing:"
                    + document.sha256
                )

            actual_size = (
                local_file.stat().st_size
            )

            if (
                    actual_size
                    != document.byte_size
            ):
                raise S3MigrationError(
                    "local_document_size_mismatch:"
                    + document.sha256
                )

            actual_sha256 = self._file_sha256(local_file)
            if actual_sha256 != document.sha256:
                raise S3MigrationError(
                    "local_document_sha256_mismatch:" + document.sha256
                )

            object_key = self.store.object_key(document.sha256)

            # 이 단계의 3,231개 object는 이미 이관됐다. 누락 또는 checksum
            # 불일치를 자동 upload로 복구하지 않고 metadata 연결 전에 중단한다.
            if not self.store.verify(
                    sha256_hex=document.sha256,
                    byte_size=document.byte_size,
            ):
                raise S3MigrationError(
                    "s3_document_verification_failed:"
                    + document.sha256
                )

            migrated.append(
                MigratedDocument(
                    sha256=document.sha256,
                    byte_size=document.byte_size,
                    object_key=object_key,
                )
            )

            migrated_bytes += (
                document.byte_size
            )

            elapsed = max(
                time.monotonic()
                - started_at,
                0.000001,
                )

            speed = (
                    migrated_bytes
                    / elapsed
            )

            remaining_bytes = max(
                total_bytes
                - migrated_bytes,
                0,
                )

            eta = (
                remaining_bytes
                / speed
                if speed > 0
                else 0
            )

            print(
                "  ✓ complete | "
                f"{self._format_bytes(migrated_bytes)}"
                f"/{self._format_bytes(total_bytes)} | "
                f"speed="
                f"{self._format_bytes(speed)}/s | "
                f"elapsed="
                f"{self._format_duration(elapsed)} | "
                f"ETA="
                f"{self._format_duration(eta)}",
                flush=True,
            )

        # limit 실행은 기존 S3 object의 read-only 검증까지만 한다.
        # DB metadata는 전체 object가 검증된 경우에만 바꾼다.
        if limit is not None:
            return MigrationResult(
                unique_binary_count=(
                    unique_binary_count
                ),
                relation_count=relation_count,
                migrated_binary_count=len(
                    migrated
                ),
                db_updated=False,
            )

        if (
                len(migrated)
                != unique_binary_count
        ):
            raise S3MigrationError(
                "not_all_unique_documents_migrated"
            )

        db_updated = False

        if write_db:
            self._update_database(
                migrated=migrated,
                expected_relation_count=(
                    relation_count
                ),
            )

            db_updated = True

        return MigrationResult(
            unique_binary_count=(
                unique_binary_count
            ),
            relation_count=relation_count,
            migrated_binary_count=len(
                migrated
            ),
            db_updated=db_updated,
        )

    def _load_documents(
            self,
    ) -> list[LocalDocument]:
        query = text(
            """
            SELECT
                content_sha256,
                MIN(byte_size) AS min_byte_size,
                MAX(byte_size) AS max_byte_size,
                MIN(storage_path) AS min_storage_path,
                MAX(storage_path) AS max_storage_path,
                COUNT(*) AS relation_count
            FROM document_sources
            WHERE download_status = 'ACQUIRED'
            GROUP BY content_sha256
            ORDER BY content_sha256
            """
        )

        with self.engine.connect() as connection:
            rows = (
                connection
                .execute(query)
                .mappings()
                .all()
            )

        documents: list[
            LocalDocument
        ] = []

        for row in rows:
            sha256 = row[
                "content_sha256"
            ]

            if not sha256:
                raise S3MigrationError(
                    "acquired_document_missing_sha256"
                )

            if (
                    row["min_byte_size"]
                    is None
                    or row["max_byte_size"]
                    is None
            ):
                raise S3MigrationError(
                    "acquired_document_missing_size:"
                    + sha256
                )

            if (
                    int(row["min_byte_size"])
                    != int(
                row["max_byte_size"]
            )
            ):
                raise S3MigrationError(
                    "duplicate_sha_size_mismatch:"
                    + sha256
                )

            if (
                    not row[
                        "min_storage_path"
                    ]
                    or not row[
                "max_storage_path"
            ]
            ):
                raise S3MigrationError(
                    "acquired_document_missing_storage_path:"
                    + sha256
                )

            if (
                    row["min_storage_path"]
                    != row["max_storage_path"]
            ):
                raise S3MigrationError(
                    "duplicate_sha_storage_path_mismatch:"
                    + sha256
                )

            documents.append(
                LocalDocument(
                    sha256=sha256,
                    byte_size=int(
                        row[
                            "min_byte_size"
                        ]
                    ),
                    storage_path=row[
                        "min_storage_path"
                    ],
                    relation_count=int(
                        row[
                            "relation_count"
                        ]
                    ),
                )
            )

        return documents

    def _resolve_local_file(
            self,
            storage_path: str,
    ) -> Path:
        relative = Path(
            storage_path
        )

        if relative.is_absolute():
            raise S3MigrationError(
                "absolute_local_storage_path_forbidden"
            )

        download_root = (
                self.root
                / "data"
                / "downloaded"
        ).resolve()

        parts = relative.parts

        if (
                len(parts) >= 2
                and parts[0] == "data"
                and parts[1] == "downloaded"
        ):
            candidate = (
                    self.root
                    / relative
            ).resolve()
        else:
            candidate = (
                    download_root
                    / relative
            ).resolve()

        try:
            candidate.relative_to(
                download_root
            )
        except ValueError as exc:
            raise S3MigrationError(
                "local_storage_path_escape"
            ) from exc

        return candidate

    def _update_database(
            self,
            migrated: list[
                MigratedDocument
            ],
            expected_relation_count: int,
    ) -> None:
        verified_at = (
            datetime.now(timezone.utc)
            .replace(tzinfo=None)
        )

        update_query = text(
            """
            UPDATE document_sources
            SET
                s3_region = :region,
                s3_bucket_name = :bucket,
                s3_object_key = :object_key,
                s3_verified_at = :verified_at
            WHERE
                download_status = 'ACQUIRED'
              AND content_sha256 = :sha256
            """
        )

        # storage_path는 지금 단계에서는 변경하지 않는다.
        # 기존 3,288 relation이 가리키는 로컬 원본 위치를
        # 유지해야 migration 재실행 시에도 다시 원본 byte를
        # 검증할 수 있다.
        # 로컬 binary 삭제 직전 별도 migration에서
        # storage_path의 legacy 제약을 제거/정리한다.
        with self.engine.begin() as connection:
            locked_rows = connection.execute(
                text(
                    """
                    SELECT content_sha256
                    FROM document_sources
                    WHERE download_status = 'ACQUIRED'
                    FOR UPDATE
                    """
                )
            ).scalars().all()
            expected_sha = {document.sha256 for document in migrated}
            if (
                    len(locked_rows) != expected_relation_count
                    or set(locked_rows) != expected_sha
            ):
                raise S3MigrationError("acquired_relation_set_changed")

            for document in migrated:
                connection.execute(
                    update_query,
                    {
                        "region":
                            self.store.region,
                        "bucket":
                            self.store.bucket,
                        "object_key":
                            document.object_key,
                        "verified_at":
                            verified_at,
                        "sha256":
                            document.sha256,
                    },
                )

            verification = (
                connection
                .execute(
                    text(
                        """
                        SELECT
                            COUNT(*) AS acquired_count,

                            SUM(
                                    s3_region IS NOT NULL
                                        AND s3_bucket_name IS NOT NULL
                                        AND s3_object_key IS NOT NULL
                                        AND s3_verified_at IS NOT NULL
                            ) AS migrated_count,

                            COUNT(
                                    DISTINCT content_sha256
                            ) AS unique_sha_count,

                            COUNT(
                                    DISTINCT s3_object_key
                            ) AS unique_s3_key_count,

                            SUM(
                                s3_region <> :region
                                OR s3_bucket_name <> :bucket
                                OR s3_object_key <> CONCAT(
                                    :prefix,
                                    '/sha256/',
                                    SUBSTRING(content_sha256, 1, 2),
                                    '/',
                                    SUBSTRING(content_sha256, 3, 2),
                                    '/',
                                    content_sha256
                                )
                            ) AS invalid_mapping_count

                        FROM document_sources

                        WHERE
                            download_status = 'ACQUIRED'
                        """
                    ),
                    {
                        "region": self.store.region,
                        "bucket": self.store.bucket,
                        "prefix": self.store.prefix,
                    },
                )
                .mappings()
                .one()
            )

            acquired_count = int(
                verification[
                    "acquired_count"
                ]
            )

            migrated_count = int(
                verification[
                    "migrated_count"
                ]
                or 0
            )

            unique_sha_count = int(
                verification[
                    "unique_sha_count"
                ]
            )

            unique_s3_key_count = int(
                verification[
                    "unique_s3_key_count"
                ]
            )

            invalid_mapping_count = int(
                verification["invalid_mapping_count"] or 0
            )

            if (
                    acquired_count
                    != expected_relation_count
            ):
                raise S3MigrationError(
                    "acquired_relation_count_changed"
                )

            if (
                    migrated_count
                    != acquired_count
            ):
                raise S3MigrationError(
                    "not_all_relations_have_s3_metadata"
                )

            if (
                    unique_sha_count
                    != unique_s3_key_count
            ):
                raise S3MigrationError(
                    "sha_to_s3_object_mapping_mismatch"
                )

            if invalid_mapping_count:
                raise S3MigrationError("invalid_s3_relation_mapping")

    @staticmethod
    def _file_sha256(file_path: Path) -> str:
        digest = hashlib.sha256()
        with file_path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def close(
            self,
    ) -> None:
        self.engine.dispose()

    @staticmethod
    def _format_bytes(
            value: float,
    ) -> str:
        units = (
            "B",
            "KiB",
            "MiB",
            "GiB",
            "TiB",
        )

        size = float(value)

        for unit in units:
            if (
                    size < 1024
                    or unit == units[-1]
            ):
                return (
                    f"{size:.2f} {unit}"
                )

            size /= 1024

        return f"{size:.2f} TiB"

    @staticmethod
    def _format_duration(
            seconds: float,
    ) -> str:
        total = max(
            0,
            int(seconds),
        )

        hours, remainder = divmod(
            total,
            3600,
        )

        minutes, secs = divmod(
            remainder,
            60,
        )

        return (
            f"{hours:02d}:"
            f"{minutes:02d}:"
            f"{secs:02d}"
        )
