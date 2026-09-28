import argparse
import json
import sys
from pathlib import Path

from biz_aid_pipeline.config.settings import ApiConfig, DbConfig, PipelineError, ROOT, credential_echo
from biz_aid_pipeline.ingestion.sample import load_pilot_sample
from biz_aid_pipeline.ingestion.service import ingest
from biz_aid_pipeline.persistence.mysql_repository import MysqlRepository
from biz_aid_pipeline.quality.structured_data_gate import render_report, validate_report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Phase 1A dev-only same-100 structured ingestion")
    parser.add_argument("--profile", required=True, choices=["dev"])
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args(argv)
    repository = None
    try:
        path = ROOT / args.report
        parent = ROOT / "harness/workspace/reports/codex"
        if path.parent != parent or path.suffix != ".md" or path.is_symlink() or path.exists() or path.resolve() != path:
            raise PipelineError("report_requires_new_direct_workspace_markdown")
        artifact = ROOT / f"harness/workspace/artifacts/codex/phase1a-structured-pipeline/structured-{args.run_id}.json"
        if artifact.exists() or artifact.is_symlink():
            raise PipelineError("report_artifact_already_exists")
        if artifact.parent.resolve() != artifact.parent:
            raise PipelineError("unsafe_report_artifact_directory")
        # 보관 경로만 Producer별로 옮긴다. 수집·정규화·DB 동작은 기존 제품 경계를 유지한다.
        artifact.parent.mkdir(parents=True, exist_ok=True)
        parent.mkdir(parents=True, exist_ok=True)
        batch = load_pilot_sample(ROOT)
        config = DbConfig.load(ROOT, args.profile)
        repository = MysqlRepository(config)
        report = ingest(repository, batch, args.run_id)
        validate_report(report)
        serialized = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        # DB와 API 인증값이 보고서에 반사됐으면 저장을 거부한다. 값이나 SQL 예외 원문은 출력하지 않는다.
        if any(credential_echo(serialized.encode(), key) for key in (config.password, ApiConfig.load(ROOT, "dev").key)):
            raise PipelineError("credential_reflection_refused")
        with artifact.open("x", encoding="utf-8") as output:
            output.write(serialized)
        with path.open("x", encoding="utf-8") as output:
            output.write(render_report(report))
        print(json.dumps({key: report[key] for key in ("run_id", "status", "input_count", "inserted", "updated", "noop", "reactivated", "soft_deleted", "failed")}))
        return 0 if report["status"] == "PASS" else 1
    except (ValueError, OSError, KeyError, TypeError):
        print("FAIL: structured ingestion; configuration/evidence/DB boundary", file=sys.stderr)
        return 1
    finally:
        if repository:
            repository.close()


if __name__ == "__main__":
    sys.exit(main())
