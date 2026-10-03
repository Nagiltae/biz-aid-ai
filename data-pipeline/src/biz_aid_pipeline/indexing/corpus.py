"""dev 전용 bounded indexing runner. 명시한 source 목록만 순서대로 기존 index_source에 넘긴다.

먼저 모든 target이 현재 parse_key로 PARSED인지 확인하고(parse gate), 하나라도 아니면 indexing을 시작하지 않는다.
source별 실패를 격리하고, 같은 run에서 이미 INDEXED인 source는 건너뛰며(resume), 종료 요청은 source 경계에서만 반영한다.
"""
import argparse
import json
import signal
import time
from pathlib import Path

from biz_aid_pipeline.config.settings import ROOT, PipelineError

RUNS = Path("data/parsed/index-runs")
# 이전 실측(Phase 4-B: 약 0.2s/chunk, source당 수십 chunk)에서 잡은 첫 source 전 추정값. 실행 뒤에는 실측 평균으로 바꾼다.
INITIAL_SECONDS_PER_SOURCE = 20.0
# Qdrant·S3·DB 같은 실행 환경 오류가 연속되면 source 문제가 아니므로 나머지를 실패로 쌓지 않고 멈춘다.
MAX_CONSECUTIVE_UNEXPECTED = 3


def read_sources(path):
    return [line.strip() for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def parse_gate(root, profile, sources):
    """현재 parse_key의 PARSED 결과가 없는 target 목록 [(sha, 사유)]. 비어 있어야 indexing을 시작한다."""
    from biz_aid_pipeline.chunking.source import current_parse_key
    from biz_aid_pipeline.config.settings import DbConfig
    from biz_aid_pipeline.parsing.models import parsing_contract
    from biz_aid_pipeline.parsing.repository import ParseResultRepository
    contract = parsing_contract()
    repository = ParseResultRepository(DbConfig.load(Path(root), profile))
    try:
        formats = dict(repository.verified_source_formats())
        missing = []
        for sha in sources:
            if sha not in formats:
                missing.append((sha, "verified_document_source_required"))
                continue
            try:
                _, key = current_parse_key(sha, formats[sha], contract)
            except PipelineError as error:
                missing.append((sha, str(error)))
                continue
            row = repository.get(sha, key)
            if row is None or row["parse_status"] != "PARSED":
                missing.append((sha, "current_parsed_artifact_required:" + (row["parse_status"] if row else "none")))
        return missing
    finally:
        repository.close()


def verify_collection(client, collection, sources, source_points):
    """완료 뒤 확인: 대상 collection이 있고, target마다 point 수가 이번 적재 결과와 같으며, pblanc_id·provenance가 빈 point가 없다.

    V1(baseline)·V2(서비스) collection이 함께 있을 수 있어 "collection이 하나뿐"은 조건이 아니다. 다른 collection은 건드리지 않는다.
    """
    from qdrant_client import models
    from biz_aid_pipeline.indexing.qdrant_store import source_filter
    counts = {sha: client.count(collection, count_filter=source_filter(sha), exact=True).count for sha in sources}
    mismatched = sorted(sha for sha in sources if counts[sha] == 0 or counts[sha] != source_points.get(sha))
    empty = client.count(collection, count_filter=models.Filter(should=[
        models.IsEmptyCondition(is_empty=models.PayloadField(key=key)) for key in ("pblanc_id", "provenance")]), exact=True).count
    distinct = client.facet(collection, key="source_sha256", limit=100000, exact=True).hits
    collections = sorted(item.name for item in client.get_collections().collections)
    total = client.count(collection, exact=True).count
    # point id가 chunk_id이므로 같은 chunk는 한 point다. source별 수가 적재 결과와 같으면 중복·잔여 point가 없다.
    return {"collection": collection, "collections": collections, "points_total": total,
            "target_points": sum(counts.values()), "sources_in_collection": len(distinct),
            "target_sources_present": sum(1 for count in counts.values() if count), "non_target_sources": len(distinct) - len(sources),
            "point_count_mismatch": mismatched, "points_missing_pblanc_or_provenance": empty,
            "ok": not mismatched and empty == 0 and collection in collections}


def snapshot(state):
    elapsed = time.time() - state["started"]
    processed = state["indexed"] + state["failed"]
    remaining = state["total"] - state["completed"]
    measured = state["processed_seconds"] / processed if processed else None
    per_source = measured or INITIAL_SECONDS_PER_SOURCE
    return {"run_id": state["run_id"], "phase": "INDEXING", "state": state["state"], "stop_reason": state["stop_reason"],
            "total": state["total"], "completed": state["completed"], "remaining": remaining, "indexed": state["indexed"],
            "failed": state["failed"], "resumed_skips": state["skipped"], "current": state["current"],
            "chunks": state["chunks"], "failure_codes": dict(sorted(state["failures"].items())),
            "elapsed_seconds": round(elapsed, 1), "avg_seconds_per_source": round(measured, 1) if measured else None,
            "eta_seconds": round(per_source * remaining, 1) if state["state"] == "RUNNING" else 0,
            "eta_basis": "measured_average" if measured else "initial_estimate", "collection": state["collection"],
            "excluded_unparsed": state.get("excluded_unparsed", 0), "final": state.get("final"),
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}


def drive(sources, index_one, done, state, write, stop_requested=lambda: False):
    """target 목록만 순서대로 처리한다. done(이 run에서 이미 INDEXED)은 건너뛴다. 한 source 실패는 기록하고 계속한다."""
    consecutive = 0
    for sha in sources:
        # BOUNDARY: 종료 요청은 새 source를 시작하기 전에만 본다. 진행 중 upsert·stale 정리를 끊지 않는다.
        if stop_requested():
            state["state"], state["stop_reason"], state["current"] = "STOPPED_SIGNAL", "stop requested", None
            return state
        if sha in done:
            state["completed"] += 1
            state["skipped"] += 1
            continue
        state["current"] = sha
        write(None, state)
        started = time.time()
        try:
            outcome = index_one(sha)
            consecutive = 0
        except PipelineError as error:
            outcome = {"source_sha256": sha, "status": "FAILED", "failure_code": str(error)}
            consecutive = 0
        except Exception:
            # RISK: Qdrant·S3·DB 예외 원문은 endpoint·credential을 담을 수 있어 고정 코드만 남긴다.
            outcome = {"source_sha256": sha, "status": "FAILED", "failure_code": "unexpected_indexing_failure"}
            consecutive += 1
        outcome["elapsed_seconds"] = round(time.time() - started, 1)
        state["processed_seconds"] += outcome["elapsed_seconds"]
        state["completed"] += 1
        if outcome["status"] == "INDEXED":
            state["indexed"] += 1
            state["chunks"] += outcome.get("chunks", 0)
            state["source_points"][sha] = outcome.get("source_points")
            state["collection"] = outcome.get("collection", state["collection"])
        else:
            # BOUNDARY: admission 보류는 완전 적재 성공이 아니다. 명시적 실패 코드로 completeness를 닫는다.
            outcome.setdefault("failure_code", "index_admission_skipped")
            state["failed"] += 1
            state["failures"][outcome["failure_code"]] = state["failures"].get(outcome["failure_code"], 0) + 1
        write(outcome, state)
        if consecutive >= MAX_CONSECUTIVE_UNEXPECTED:
            state["state"], state["stop_reason"], state["current"] = "STOPPED_ENVIRONMENT", "unexpected_indexing_failure", None
            return state
    state["state"], state["current"] = "COMPLETED", None
    return state


def run_indexing(root, profile, run_id, sources, namespace, parsed_only=False):
    if profile != "dev":
        raise PipelineError("indexing_requires_dev_profile")
    directory = Path(root) / RUNS / run_id
    directory.mkdir(parents=True, exist_ok=True)
    results_path = directory / "results.jsonl"
    source_points = {}
    if results_path.exists():
        for line in results_path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row.get("status") == "INDEXED":
                source_points[row["source_sha256"]] = row.get("source_points")
    done = set(source_points)
    state = {"run_id": run_id, "state": "RUNNING", "stop_reason": None, "total": len(sources), "completed": 0,
             "indexed": 0, "failed": 0, "skipped": 0, "current": None, "chunks": 0, "failures": {},
             "processed_seconds": 0.0, "collection": None, "started": time.time(), "source_points": source_points,
             "final": None, "excluded_unparsed": 0}
    results = results_path.open("a", encoding="utf-8")

    def write(outcome, current):
        if outcome is not None:
            results.write(json.dumps(outcome, ensure_ascii=False) + "\n")
            results.flush()
        temporary = directory / "progress.json.tmp"
        temporary.write_text(json.dumps(snapshot(current), ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(directory / "progress.json")

    try:
        state["state"] = "PARSE_GATE"
        write(None, state)
        missing = parse_gate(root, profile, sources)
        if missing and parsed_only:
            # 서비스 범위 적재(V2)는 현재 parser로 PARSED된 문서만 넣는다. 제외 목록과 사유는 그대로 남긴다(조용히 버리지 않음).
            (directory / "parse-gate-excluded.json").write_text(
                json.dumps([{"source_sha256": sha, "reason": reason} for sha, reason in missing], indent=2), encoding="utf-8")
            excluded = {sha for sha, _ in missing}
            sources = [sha for sha in sources if sha not in excluded]
            state["total"], state["excluded_unparsed"], missing = len(sources), len(excluded), []
        # BOUNDARY: 일부만 현재 parser 결과인 dataset을 완성본으로 적재하지 않는다. 실패 목록을 남기고 멈춘다.
        if missing:
            (directory / "parse-gate-failures.json").write_text(
                json.dumps([{"source_sha256": sha, "reason": reason} for sha, reason in missing], indent=2), encoding="utf-8")
            state["state"], state["stop_reason"] = "PARSE_GATE_FAILED", f"{len(missing)} sources without current PARSED"
            return state
        state["state"] = "RUNNING"
        from qdrant_client import QdrantClient
        from biz_aid_pipeline.indexing.embedder import BgeM3Embedder, indexing_contract
        from biz_aid_pipeline.indexing.pipeline import index_source
        from biz_aid_pipeline.indexing.qdrant_store import collection_name, qdrant_url
        contract = indexing_contract()
        embedder = BgeM3Embedder(contract)
        client = QdrantClient(url=qdrant_url(profile))
        stop = []
        # WHY: 신호로 바로 끝내면 source의 upsert와 stale 정리 사이에서 끊길 수 있다. 신호는 다음 source 경계의 종료 요청이다.
        for signum in (signal.SIGTERM, signal.SIGINT):
            signal.signal(signum, lambda *_: stop.append(True))
        drive(sources, lambda sha: index_source(sha, embedder, client, contract, profile, Path(root), namespace=namespace), done,
              state, write, lambda: bool(stop))
        if state["state"] == "COMPLETED" and state["failed"] == 0:
            state["collection"] = collection_name(contract, embedder.identity["embedding_key"], namespace)
            state["final"] = verify_collection(client, state["collection"], sources, state["source_points"])
            if not state["final"]["ok"]:
                state["state"], state["stop_reason"] = "VERIFY_FAILED", "final collection check failed"
        return state
    finally:
        write(None, state)
        results.close()


def status_text(root, run_id):
    path = Path(root) / RUNS / run_id / "progress.json"
    if not path.exists():
        return f"[Corpus Index] {run_id} not started"
    snap = json.loads(path.read_text(encoding="utf-8"))
    eta = snap["eta_seconds"]
    avg = snap["avg_seconds_per_source"]
    lines = [f"[Corpus Index] {snap['run_id']} state={snap['state']}",
             f"completed: {snap['completed']} / {snap['total']}  remaining: {snap['remaining']}  indexed: {snap['indexed']}  "
             f"failed: {snap['failed']}  chunks: {snap['chunks']}",
             f"current: {(snap['current'] or '-')[:12]}  elapsed: {int(snap['elapsed_seconds'] // 60)}m  "
             f"avg/source: {f'{avg}s' if avg else '-'}  ETA (estimate, {snap['eta_basis']}): {int(eta // 60)}m {int(eta % 60)}s"]
    if snap.get("excluded_unparsed"):
        lines.append(f"excluded (not currently PARSED, see parse-gate-excluded.json): {snap['excluded_unparsed']}")
    if snap["stop_reason"]:
        lines.append(f"stop_reason: {snap['stop_reason']}")
    if snap.get("final"):
        lines.append("final: " + json.dumps(snap["final"], ensure_ascii=False))
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="dev-only bounded indexing over an explicit source list")
    parser.add_argument("--profile", choices=["dev"], required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--status", action="store_true", help="진행 상태만 출력")
    parser.add_argument("--sources-file", help="index할 content SHA 목록(한 줄에 하나)")
    # V1 collection은 baseline 재현용으로 동결했다. 적재는 항상 namespace collection(예: v2)에 한다.
    parser.add_argument("--collection-namespace", help="적재할 collection namespace(예: v2). --status가 아니면 필수")
    parser.add_argument("--parsed-only", action="store_true", help="현재 parse_key로 PARSED된 source만 적재(나머지는 제외 목록에 기록)")
    args = parser.parse_args(argv)
    if args.status:
        print(status_text(ROOT, args.run_id))
        return 0
    if not args.sources_file or not args.collection_namespace:
        parser.error("--sources-file and --collection-namespace are required unless --status")
    state = run_indexing(ROOT, args.profile, args.run_id, read_sources(args.sources_file), args.collection_namespace,
                         args.parsed_only)
    print(status_text(ROOT, args.run_id))
    return 0 if state["state"] == "COMPLETED" and state["failed"] == 0 else 1
