"""AI 개선 0단계(1): 자격 판정 조건 분할 측정. 기존 코드·기대값은 바꾸지 않고 현재 동작만 잰다.

- 공고 3개(123260·117611·120174)를 Bedrock으로 1회씩 순차 판정한다(재시도 없음).
- cases-v2 Bedrock 결과 파일의 단일 판정(V2-19·20)과 맞춤 추천 안 판정 결과도 같은 기준으로 센다(LLM 재호출 없음).
- 제출서류/절차 성격·중복 판단은 문자열 규칙이다(사람 확인용으로 해당 조건 문장을 함께 남긴다).
"""
import argparse
import difflib
import json
import os
import re
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data-pipeline/src"))
sys.path.insert(0, str(ROOT / "evals/cases-v2"))

TARGETS = ("PBLN_000000000123260", "PBLN_000000000117611", "PBLN_000000000120174")
# 합성 기업정보(실제 회사 아님). cases-v2 V2-19의 값에 기업 지역만 더해 세 공고에 같은 입력을 준다.
PROFILE = {"region": "경기도", "company_size": "중소기업", "business_status": "영업중"}
AS_OF = "2026-10-04"
# WHY: "자격 요건"이 아니라 "무엇을 내고 어떻게 신청하는지"를 말하는 조건을 찾는 단어. 규칙 기반이라 과소·과대 집계가 있을 수 있다.
PROCEDURE_WORDS = ("제출", "서류", "증빙", "사본", "신청서", "확인서", "증명서", "등록증", "첨부", "서식", "작성", "접수",
                   "온라인 신청", "신청 방법", "신청방법", "절차", "동의서", "서약", "발급")
DUPLICATE_RATIO = 0.85


def normalize(text):
    return re.sub(r"[\s·,.()\[\]~:;/\-]+", "", text or "")


def analyze(criteria):
    """조건 목록 → 개수·제출서류/절차 성격·중복 개수. 중복은 정규화 문장이 같거나 유사도 0.85 이상인 뒤쪽 조건이다."""
    texts = [item.get("criterion") or item.get("requirement") or "" for item in criteria]
    procedure = [text for text in texts if any(word in text for word in PROCEDURE_WORDS)]
    duplicates, seen = [], []
    for text in texts:
        key = normalize(text)
        match = next((other for other in seen if key == other or difflib.SequenceMatcher(None, key, other).ratio() >= DUPLICATE_RATIO), None)
        if match is not None:
            duplicates.append(text)
        seen.append(key)
    return {"criteria_count": len(texts), "procedure_count": len(procedure), "duplicate_count": len(duplicates),
            "procedure_criteria": procedure, "duplicate_criteria": duplicates, "criteria": texts,
            "results": [item.get("result") for item in criteria]}


def live(limits):
    os.environ["LLM_PROVIDER"] = "bedrock"
    # BOUNDARY: 자격 증명은 SDK credential chain의 로컬 profile 이름만 지정한다(키 값은 읽지 않음).
    os.environ["AWS_PROFILE"] = "bizaid-dev"
    from biz_aid_pipeline.config.settings import PipelineError
    from biz_aid_pipeline.eligibility.profile import CompanyProfileSnapshot
    from biz_aid_pipeline.runtime import ServiceRuntime
    from evaluate import MeteredProvider
    runtime = ServiceRuntime("dev", collection_namespace="v2", tracer=None)
    runtime.provider = MeteredProvider(runtime.provider)
    rows = []
    try:
        for pblanc_id in TARGETS:
            offset, started = len(runtime.provider.calls), time.monotonic()
            row = {"source": "live", "pblanc_id": pblanc_id}
            try:
                result = runtime.evaluate_eligibility(pblanc_id, CompanyProfileSnapshot.from_dict(PROFILE), date.fromisoformat(AS_OF))
                row.update(outcome="COMPLETED", status=result.get("status"), **analyze(result.get("criteria") or []))
            except PipelineError as error:
                row.update(outcome="FAILED", error_code=str(error))
            except Exception as error:
                # RISK: SDK 예외 원문에는 요청 상세가 섞일 수 있어 종류만 남긴다.
                row.update(outcome="FAILED", error_code=type(error).__name__)
            calls = runtime.provider.calls[offset:]
            row.update(seconds=round(time.monotonic() - started, 2), llm_calls=calls)
            row["limit_reached"] = (row.get("error_code") == "eligibility_output_limit_reached"
                                    or any((call.get("output_tokens") or 0) >= limits["max_output_tokens"] for call in calls)
                                    or row.get("criteria_count", 0) >= limits["max_criteria"])
            rows.append(row)
            print(json.dumps({key: row.get(key) for key in ("pblanc_id", "outcome", "status", "criteria_count", "procedure_count",
                                                             "duplicate_count", "seconds", "limit_reached")}, ensure_ascii=False), flush=True)
    finally:
        runtime.close()
    return rows


def from_cases(path, limits):
    """cases-v2 결과에서 판정 결과를 다시 센다. 맞춤 추천은 첫 LLM 호출이 질문 조건 추출이고 이후가 공고별 판정이다."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = []
    for case in data["cases"]:
        actual, calls = case.get("actual") or {}, case.get("llm_calls") or []
        if case["evaluation_type"] == "ELIGIBILITY" and actual.get("criteria") is not None:
            items = [(actual, calls[-1] if calls else {})]
        elif case["evaluation_type"] == "PERSONALIZED":
            judged = [entry for entry in actual.get("evaluations", []) if entry.get("eligibility")]
            items = list(zip([entry["eligibility"] for entry in judged], calls[1:]))
        else:
            continue
        for result, call in items:
            row = {"source": "cases-v2:" + case["case_id"], "pblanc_id": result.get("pblanc_id"), "outcome": "COMPLETED",
                   "status": result.get("status"), "seconds": result.get("llm_seconds"), "llm_calls": [call],
                   **analyze(result.get("criteria") or [])}
            row["limit_reached"] = ((call.get("output_tokens") or 0) >= limits["max_output_tokens"]
                                    or row["criteria_count"] >= limits["max_criteria"])
            rows.append(row)
    return rows


def main():
    parser = argparse.ArgumentParser(description="Eligibility criteria split measurement; sequential Bedrock, no retry, no overwrite")
    parser.add_argument("--cases-results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output_exists")
    from biz_aid_pipeline.eligibility.service import eligibility_contract
    limits = {key: eligibility_contract()["criterion_output"][key] for key in ("max_output_tokens", "max_criteria")}
    started = datetime.now(timezone.utc).isoformat()
    rows = live(limits) + from_cases(args.cases_results, limits)
    report = {"started_at": started, "profile": PROFILE, "as_of": AS_OF, "limits": limits, "procedure_words": PROCEDURE_WORDS,
              "duplicate_rule": f"normalized equal or SequenceMatcher ratio >= {DUPLICATE_RATIO}", "rows": rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
