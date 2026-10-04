"""dev 단일 자격 판정 1회 실행(묶음5-1 항목1: 출력 상한 2560 확인용). 반복·재시도 없이 결과 JSON만 남긴다.

예: BIZAID_DOCLING_ARTIFACTS_PATH=... .venv/bin/python scripts/run_single_eligibility.py --provider bedrock \\
      --pblanc-id PBLN_000000000120174 --output harness/workspace/artifacts/development/<task>/result.json
"""
import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data-pipeline/src"))
sys.path.insert(0, str(ROOT / "evals/cases-v2"))
# 동결 V2-16 사례와 같은 합성 기업정보(실제 회사 아님).
DEFAULT_PROFILE = {"region": "경기도", "company_size": "소상공인", "business_status": "영업중"}


def main():
    parser = argparse.ArgumentParser(description="One dev eligibility call; sequential, no retry, no overwrite")
    parser.add_argument("--provider", choices=["ollama", "bedrock"], required=True)
    parser.add_argument("--pblanc-id", required=True)
    parser.add_argument("--as-of", default="2026-10-04")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output_exists")
    os.environ["LLM_PROVIDER"] = args.provider
    if args.provider == "bedrock":
        # BOUNDARY: 자격 증명은 SDK credential chain의 로컬 profile 이름만 지정한다(키 값은 읽지 않음).
        os.environ["AWS_PROFILE"] = "bizaid-dev"
    from biz_aid_pipeline.config.settings import PipelineError
    from biz_aid_pipeline.eligibility.profile import CompanyProfileSnapshot
    from biz_aid_pipeline.eligibility.service import eligibility_contract
    from biz_aid_pipeline.runtime import ServiceRuntime
    from evaluate import MeteredProvider

    runtime = ServiceRuntime("dev", collection_namespace="v2", tracer=None)
    runtime.provider = MeteredProvider(runtime.provider)
    limits = eligibility_contract()["criterion_output"]
    record = {"pblanc_id": args.pblanc_id, "provider": args.provider, "company_profile": DEFAULT_PROFILE, "as_of": args.as_of,
              "limits": {key: limits[key] for key in ("max_output_tokens", "max_criteria")},
              "started_at": datetime.now(timezone.utc).isoformat()}
    started = time.monotonic()
    try:
        result = runtime.evaluate_eligibility(args.pblanc_id, CompanyProfileSnapshot.from_dict(DEFAULT_PROFILE),
                                              date.fromisoformat(args.as_of))
        criteria = result.get("criteria") or []
        record.update(outcome="COMPLETED", status=result.get("status"), criteria_count=len(criteria),
                      criteria=[{key: item.get(key) for key in ("requirement", "result", "profile_fields")} for item in criteria])
    except PipelineError as error:
        record.update(outcome="FAILED", error_code=str(error))
    except Exception as error:
        # RISK: SDK 예외 원문에는 요청 상세가 섞일 수 있어 종류만 남긴다.
        record.update(outcome="FAILED", error_code=type(error).__name__)
    finally:
        runtime.close()
    record.update(seconds=round(time.monotonic() - started, 2), llm_calls=runtime.provider.calls)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: record.get(key) for key in ("outcome", "status", "criteria_count", "error_code", "seconds")}, ensure_ascii=False))
    return 0 if record["outcome"] == "COMPLETED" else 1


if __name__ == "__main__":
    sys.exit(main())
