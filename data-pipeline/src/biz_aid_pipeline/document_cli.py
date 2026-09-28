import argparse
import json
import sys

from biz_aid_pipeline.config.settings import PipelineError, ROOT
from biz_aid_pipeline.documents.service import run, verify_run


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        raise PipelineError("invalid_document_cli_arguments")


def main(argv=None):
    parser = SafeParser(description="dev-only Phase 2 full document acquisition; no parsing")
    sub = parser.add_subparsers(dest="command", required=True)
    collect = sub.add_parser("collect")
    collect.add_argument("--profile", choices=["dev"], required=True)
    collect.add_argument("--run-id", required=True)
    collect.add_argument("--resume", action="store_true")
    verify = sub.add_parser("verify")
    verify.add_argument("--run-id", required=True)
    try:
        args = parser.parse_args(argv)
        if args.command == "verify":
            report = verify_run(ROOT, args.run_id)
        else:
            def progress(processed, total, outcome):
                if processed % 50 == 0 or outcome != "ACQUIRED":
                    print(json.dumps({"processed_relations": processed, "total_relations": total,
                                      "outcome": outcome}), flush=True)
            report = run(ROOT, args.profile, args.run_id, resume=args.resume, progress=progress)
        keys = ("run_id", "status", "support_program_count", "total_candidate_relations",
                "unique_source_url_count", "attempted_downloads", "success_count", "failed_count",
                "pdf_count", "hwp_count", "hwpx_count", "other_unknown_count",
                "duplicate_content_sha_count", "persisted_metadata_count")
        print(json.dumps({key: report.get(key) for key in keys}, ensure_ascii=False))
        return 0 if report["status"] == "PASS" else 1
    except (ValueError, OSError, KeyError, TypeError):
        # URL·응답·DB 예외에는 인증정보가 반사될 수 있어 고정 메시지만 출력한다.
        print("FAIL: document acquisition configuration/evidence/DB boundary; details withheld", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
