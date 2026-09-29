import argparse
import json
import sys

from biz_aid_pipeline.config.settings import PipelineError, ROOT
from biz_aid_pipeline.parsing.orchestration import run_batch, run_source


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        raise PipelineError("invalid_parsing_cli_arguments")


def main(argv=None, runner=run_source, batch_runner=run_batch):
    parser = SafeParser(description="dev-only bounded document parsing and persistence")
    parser.add_argument("--profile", choices=["dev"], required=True)
    parser.add_argument("--source-sha256", action="append", required=True)
    try:
        args = parser.parse_args(argv)
        if len(args.source_sha256) == 1:
            execution = runner(ROOT, args.profile, args.source_sha256[0])
            print(json.dumps(execution.summary(), ensure_ascii=False, sort_keys=True))
            return 0 if execution.status == "PARSED" else 1
        execution = batch_runner(ROOT, args.profile, args.source_sha256, runner=runner)
        print(json.dumps(execution.summary(), ensure_ascii=False, sort_keys=True))
        return 0 if execution.status == "PASS" else 1
    except (ValueError, OSError, KeyError, TypeError):
        # S3·DB·parser 예외에는 credential이나 provider 응답이 섞일 수 있어 고정 문구만 출력한다.
        print("FAIL: bounded parsing/storage/DB boundary; details withheld", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
