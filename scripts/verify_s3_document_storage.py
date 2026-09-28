from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from sqlalchemy import (
    create_engine,
    text,
)
from sqlalchemy.engine import URL


PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)

DATA_PIPELINE_SRC = (
        PROJECT_ROOT
        / "data-pipeline"
        / "src"
)

sys.path.insert(
    0,
    str(DATA_PIPELINE_SRC),
)


from biz_aid_pipeline.config.settings import (
    DbConfig,
    ROOT,
    S3Config,
)
from biz_aid_pipeline.storage import (
    S3DocumentStore,
)


class S3StorageVerificationError(
    RuntimeError
):
    pass


def format_bytes(
        value: float,
) -> str:
    units = (
        "B",
        "KB",
        "MB",
        "GB",
        "TB",
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

    return f"{size:.2f} TB"


def format_duration(
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


def create_db_engine(
        config: DbConfig,
):
    url = URL.create(
        "mysql+pymysql",
        username=config.user,
        password=config.password,
        host=config.host,
        port=config.port,
        database=config.database,
        query={
            "charset": "utf8mb4",
        },
    )

    return create_engine(
        url,
        future=True,
        pool_pre_ping=True,
        hide_parameters=True,
    )


def load_documents(
        engine,
):
    query = text(
        """
        SELECT
            content_sha256,

            MIN(
                    byte_size
            ) AS min_byte_size,

            MAX(
                    byte_size
            ) AS max_byte_size,

            COUNT(*) AS relation_count,

            SUM(
                    s3_region IS NULL
                        OR s3_bucket_name IS NULL
                        OR s3_object_key IS NULL
                        OR s3_verified_at IS NULL
            ) AS missing_s3_metadata,

            COUNT(
                    DISTINCT s3_region
            ) AS region_count,

            MIN(
                    s3_region
            ) AS s3_region,

            COUNT(
                    DISTINCT s3_bucket_name
            ) AS bucket_count,

            MIN(
                    s3_bucket_name
            ) AS s3_bucket_name,

            COUNT(
                    DISTINCT s3_object_key
            ) AS object_key_count,

            MIN(
                    s3_object_key
            ) AS s3_object_key

        FROM document_sources

        WHERE
            download_status = 'ACQUIRED'

        GROUP BY
            content_sha256

        ORDER BY
            content_sha256
        """
    )

    with engine.connect() as connection:
        return (
            connection
            .execute(query)
            .mappings()
            .all()
        )


def verify_database_shape(
        rows,
        store,
):
    if not rows:
        raise S3StorageVerificationError(
            "no_acquired_documents"
        )

    relation_count = 0
    total_bytes = 0

    for row in rows:
        sha256 = row[
            "content_sha256"
        ]

        if not sha256:
            raise S3StorageVerificationError(
                "missing_content_sha256"
            )

        if (
                row["min_byte_size"]
                != row["max_byte_size"]
        ):
            raise S3StorageVerificationError(
                "duplicate_sha_size_mismatch:"
                + sha256
            )

        if (
                int(
                    row[
                        "missing_s3_metadata"
                    ]
                    or 0
                )
                != 0
        ):
            raise S3StorageVerificationError(
                "incomplete_s3_metadata:"
                + sha256
            )

        if (
                int(
                    row[
                        "region_count"
                    ]
                )
                != 1
        ):
            raise S3StorageVerificationError(
                "inconsistent_s3_region:"
                + sha256
            )

        if (
                int(
                    row[
                        "bucket_count"
                    ]
                )
                != 1
        ):
            raise S3StorageVerificationError(
                "inconsistent_s3_bucket:"
                + sha256
            )

        if (
                int(
                    row[
                        "object_key_count"
                    ]
                )
                != 1
        ):
            raise S3StorageVerificationError(
                "inconsistent_s3_object_key:"
                + sha256
            )

        if (
                row["s3_region"]
                != store.region
        ):
            raise S3StorageVerificationError(
                "unexpected_s3_region:"
                + sha256
            )

        if (
                row[
                    "s3_bucket_name"
                ]
                != store.bucket
        ):
            raise S3StorageVerificationError(
                "unexpected_s3_bucket:"
                + sha256
            )

        expected_key = (
            store.object_key(
                sha256
            )
        )

        if (
                row[
                    "s3_object_key"
                ]
                != expected_key
        ):
            raise S3StorageVerificationError(
                "unexpected_s3_object_key:"
                + sha256
            )

        # storage_path는 현재 legacy 로컬 경로를
        # 유지할 수 있으므로 S3 object key와
        # 같아야 한다는 조건을 두지 않는다.
        # 실제 영구 저장 위치 검증은
        # 저장 위치 필드인 s3_region / bucket / object_key /
        # verified_at 조합을 기준으로 수행한다.

        relation_count += int(
            row[
                "relation_count"
            ]
        )

        total_bytes += int(
            row[
                "min_byte_size"
            ]
        )

    return (
        relation_count,
        total_bytes,
    )


def verify_s3(
        rows,
        store,
        full_readback: bool,
):
    started = (
        time.monotonic()
    )

    verified_bytes = 0

    total_bytes = sum(
        int(
            row[
                "min_byte_size"
            ]
        )
        for row in rows
    )

    total = len(rows)

    for index, row in enumerate(
            rows,
            start=1,
    ):
        sha256 = row[
            "content_sha256"
        ]

        byte_size = int(
            row[
                "min_byte_size"
            ]
        )

        if not store.verify(
                sha256_hex=sha256,
                byte_size=byte_size,
        ):
            raise S3StorageVerificationError(
                "s3_head_verification_failed:"
                + sha256
            )

        if full_readback:
            store.read(
                sha256_hex=sha256,
                byte_size=byte_size,
            )

        verified_bytes += (
            byte_size
        )

        elapsed = max(
            time.monotonic()
            - started,
            0.000001,
            )

        speed = (
                verified_bytes
                / elapsed
        )

        remaining = max(
            total_bytes
            - verified_bytes,
            0,
            )

        eta = (
            remaining
            / speed
            if speed > 0
            else 0
        )

        print(
            f"[{index}/{total}] "
            f"{index / total * 100:6.2f}% | "
            f"{format_bytes(verified_bytes)}"
            f"/{format_bytes(total_bytes)} | "
            f"elapsed="
            f"{format_duration(elapsed)} | "
            f"ETA="
            f"{format_duration(eta)}",
            flush=True,
        )

    return verified_bytes


def main():
    parser = argparse.ArgumentParser(
        description=(
            "document_sources의 S3 metadata와 "
            "AWS S3 object 무결성을 검증한다."
        )
    )

    parser.add_argument(
        "--profile",
        choices=[
            "dev",
        ],
        default="dev",
    )

    parser.add_argument(
        "--full-readback",
        action="store_true",
        help=(
            "HEAD checksum뿐 아니라 "
            "모든 S3 object의 실제 byte를 "
            "다시 읽어 SHA-256을 검증한다."
        ),
    )

    args = (
        parser.parse_args()
    )

    db_config = DbConfig.load(
        ROOT,
        args.profile,
    )

    s3_config = S3Config.load(
        ROOT,
        args.profile,
    )

    store = S3DocumentStore(
        bucket=s3_config.bucket,
        region=s3_config.region,
        prefix=s3_config.prefix,
    )

    engine = create_db_engine(
        db_config
    )

    try:
        rows = load_documents(
            engine
        )

        (
            relation_count,
            total_bytes,
        ) = verify_database_shape(
            rows,
            store,
        )

        print(
            "database verification passed"
        )

        print(
            f"unique_binaries="
            f"{len(rows)}"
        )

        print(
            f"relations="
            f"{relation_count}"
        )

        print(
            f"unique_bytes="
            f"{total_bytes}"
        )

        verified_bytes = verify_s3(
            rows,
            store,
            args.full_readback,
        )

        print()

        print(
            "S3 document storage "
            "verification PASS"
        )

        print(
            f"verified_unique_binaries="
            f"{len(rows)}"
        )

        print(
            f"verified_relations="
            f"{relation_count}"
        )

        print(
            f"verified_bytes="
            f"{verified_bytes}"
        )

        print(
            f"full_readback="
            f"{args.full_readback}"
        )

        return 0

    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
