from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
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
from biz_aid_pipeline.storage.s3_document_store import (
    S3DocumentStore,
)
from biz_aid_pipeline.storage.s3_migration import (
    S3MigrationService,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description=(
            "기존 Phase 2 S3 object를 read-only 검증하고 "
            "document_sources metadata를 연결한다."
        )
    )

    result.add_argument(
        "--profile",
        choices=["dev"],
        default="dev",
    )

    result.add_argument(
        "--limit",
        type=int,
        default=None,
        help=(
            "HEAD 검증할 고유 binary 개수. "
            "지정하면 DB metadata는 변경하지 않는다."
        ),
    )

    result.add_argument(
        "--write-db",
        action="store_true",
        help=(
            "모든 S3 binary 검증 후 "
            "document_sources의 S3 metadata를 기록한다."
        ),
    )

    return result


def main() -> int:
    args = parser().parse_args()

    db_config = DbConfig.load(
        root=ROOT,
        profile=args.profile,
    )

    s3_config = S3Config.load(
        root=ROOT,
        profile=args.profile,
    )

    store = S3DocumentStore(
        bucket=s3_config.bucket,
        region=s3_config.region,
        prefix=s3_config.prefix,
    )

    migration = S3MigrationService(
        db_config=db_config,
        s3_config=s3_config,
        store=store,
        root=ROOT,
    )

    result = migration.migrate(
        limit=args.limit,
        write_db=args.write_db,
    )

    print()
    print("S3 document metadata linking completed")
    print(
        f"unique_binary_count="
        f"{result.unique_binary_count}"
    )
    print(
        f"relation_count="
        f"{result.relation_count}"
    )
    print(
        f"migrated_binary_count="
        f"{result.migrated_binary_count}"
    )
    print(
        f"db_updated="
        f"{result.db_updated}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
