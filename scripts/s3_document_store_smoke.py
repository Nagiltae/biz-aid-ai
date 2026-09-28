from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_PIPELINE_SRC = PROJECT_ROOT / "data-pipeline" / "src"

sys.path.insert(
    0,
    str(DATA_PIPELINE_SRC),
)


from biz_aid_pipeline.config.settings import DbConfig, ROOT, S3Config
from biz_aid_pipeline.storage import S3DocumentStore
from biz_aid_pipeline.storage.s3_migration import S3MigrationService


def main() -> None:
    # .env.dev를 프로젝트의 기존 설정 시스템으로 읽는다.
    config = S3Config.load(
        root=ROOT,
        profile="dev",
    )

    store = S3DocumentStore(
        bucket=config.bucket,
        region=config.region,
        prefix=config.prefix,
    )

    migration = S3MigrationService(
        root=ROOT,
        db_config=DbConfig.load(ROOT, "dev"),
        s3_config=config,
        store=store,
    )
    try:
        # Phase 2.5 이후 smoke도 기존 object 한 건을 HEAD 검증할 뿐
        # 새 object를 만들거나 기존 object를 덮어쓰지 않는다.
        result = migration.migrate(limit=1, write_db=False)
    finally:
        migration.close()

    print("S3 read-only smoke PASS")
    print(f"verified_objects={result.migrated_binary_count}")


if __name__ == "__main__":
    main()
