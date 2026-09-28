import argparse
import json
import sys

from biz_aid_pipeline.bizinfo.raw_snapshot import verify_full_snapshot
from biz_aid_pipeline.config.settings import ApiConfig, PipelineError, ROOT, read_json
from biz_aid_pipeline.ingestion.full_sync import ARTIFACT_ROOT, full_contract, preflight, run_full_sync


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        raise PipelineError("invalid_cli_arguments")


def main(argv=None):
    parser = SafeParser(description="dev-only explicit FULL; first live reconciliation is DRY_RUN only")
    sub = parser.add_subparsers(dest="command", required=True)
    collect = sub.add_parser("collect")
    collect.add_argument("--profile", required=True, choices=["dev"])
    collect.add_argument("--run-id", required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--run-id", required=True)
    try:
        args = parser.parse_args(argv)
        if args.command == "verify":
            from biz_aid_pipeline.bizinfo.raw_snapshot import safe_path, valid_run_id
            valid_run_id(args.run_id)
            provenance = read_json(safe_path(ROOT, f"{ARTIFACT_ROOT}/{args.run_id}/acquisition.json"))
            batch = verify_full_snapshot(ROOT, args.run_id, provenance, ApiConfig.load(ROOT, "dev").key)
            report = preflight(batch, args.run_id)
            print(json.dumps({"snapshot_preflight": report["status"], "items": report["input_count"],
                              "unique_ids": report["unique_pblanc_id_count"], "duplicates": report["duplicate_count"]}))
            return 0 if report["status"] == "PASS" else 1
        full_contract(ROOT)
        def progress(number, outcome, count, total):
            print(json.dumps({"page": number, "outcome": outcome, "item_count": count, "observed_totalCount": total}), flush=True)
        report = run_full_sync(ROOT, args.profile, args.run_id, progress=progress)
        print(json.dumps({key: report[key] for key in ("run_id", "status", "expected_total_count", "input_count",
            "unique_pblanc_id_count", "duplicate_count", "invalid_pblanc_id_count", "inserted", "updated", "noop",
            "reactivated", "soft_delete_candidate_count", "soft_deleted", "mysql_final_row_count")}))
        return 0 if report["status"] == "PASS" else 1
    except (ValueError, OSError, KeyError, TypeError):
        # URL·DB 예외·CLI 입력에 인증값이 있을 수 있어 고정 메시지만 출력한다.
        print("FAIL: full sync argument/configuration/snapshot/DB boundary; details withheld", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
