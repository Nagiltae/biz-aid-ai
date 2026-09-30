"""dev 전용 corpus parsing. enabled format의 unique content SHA를 결정적 순서로 기존 orchestrate_source에 넘긴다.

현재 parse_key 결과가 이미 있으면 건너뛰고(resume), source별 실패를 격리하며, 진행 상태를 파일로 남긴다.
parser는 자식 process 하나에서 순차 실행한다. 제한 시간을 넘긴 source는 자식을 종료해 timeout으로 기록하고 이어서 진행한다.
"""
import argparse
import json
import multiprocessing
import resource
import signal
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from biz_aid_pipeline.config.settings import ROOT, PipelineError
from biz_aid_pipeline.parsing.models import parse_key, parsing_contract
from biz_aid_pipeline.parsing.router import route_for

RUNS = Path("data/parsed/corpus-runs")


def select_sources(rows, enabled_formats):
    """(content_sha256, detected_format) 행에서 enabled format의 unique SHA만 SHA 오름차순으로 고른다."""
    chosen = {}
    for sha, detected in rows:
        if detected in enabled_formats:
            chosen.setdefault(sha, detected)
    return sorted(chosen.items())


@dataclass
class Progress:
    run_id: str
    total: int
    target: int | None = None
    started_at: float = field(default_factory=time.time)
    completed: int = 0
    skipped: int = 0
    statuses: dict = field(default_factory=dict)
    failures: dict = field(default_factory=dict)
    current: str | None = None
    state: str = "RUNNING"
    stop_reason: str | None = None

    def record(self, status):
        self.completed += 1
        self.statuses[status] = self.statuses.get(status, 0) + 1

    def snapshot(self):
        elapsed = time.time() - self.started_at
        processed = self.completed - self.skipped
        target = min(self.target, self.total) if self.target else self.total
        return {"run_id": self.run_id, "state": self.state, "stop_reason": self.stop_reason, "total": self.total,
                "target": target, "completed": self.completed, "remaining": target - self.completed, "skipped": self.skipped,
                "processed": processed, "statuses": dict(sorted(self.statuses.items())),
                "failure_codes": dict(sorted(self.failures.items())), "current": self.current,
                "elapsed_seconds": round(elapsed, 1), "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}


# 저장소·인증 계열 실패가 연속되면 source 문제가 아니라 실행 환경 문제이므로 나머지를 실패로 기록하지 않고 멈춘다.
ENVIRONMENT_FAILURES = ("document_source_s3_read_failure", "parsed_artifact_storage_failure", "unexpected_execution_failure",
                        "parse_result_schema_unavailable_run_flyway", "worker_crashed")


def drive(sources, key_for, existing_status, execute, progress, skip_statuses, write, max_environment_failures=3,
          max_completed=None, stop_requested=lambda: False):
    """source를 순서대로 실행한다. 한 source의 실패는 기록만 하고 다음 source로 넘어간다.

    멈춤 판단은 source 경계에서만 한다. 실행 중인 source는 persistence까지 끝난 뒤에 멈춘다.
    """
    consecutive = 0
    for sha, detected in sources:
        # BOUNDARY: 상한(완료 = 처리 + skip)이나 종료 요청은 새 source를 시작하기 전에만 확인한다.
        if max_completed is not None and progress.completed >= max_completed:
            progress.state, progress.stop_reason, progress.current = "STOPPED_LIMIT", f"max_completed={max_completed}", None
            return progress
        if stop_requested():
            progress.state, progress.stop_reason, progress.current = "STOPPED_SIGNAL", "stop requested", None
            return progress
        progress.current = sha
        key = key_for(sha, detected)
        status = existing_status(sha, key) if key else None
        if status in skip_statuses:
            # BOUNDARY: 현재 parse_key의 결과가 이미 있으면 재처리하지 않는다(immutable artifact·resume).
            progress.skipped += 1
            progress.record(status)
            write(sha, detected, {"status": status, "action": "SKIPPED_CURRENT_KEY", "parse_key": key}, progress)
            continue
        started = time.time()
        outcome = execute(sha)
        outcome["elapsed_seconds"] = round(time.time() - started, 1)
        progress.record(outcome["status"])
        if outcome.get("failure_code"):
            progress.failures[outcome["failure_code"]] = progress.failures.get(outcome["failure_code"], 0) + 1
        write(sha, detected, outcome, progress)
        consecutive = consecutive + 1 if outcome.get("failure_code") in ENVIRONMENT_FAILURES else 0
        if consecutive >= max_environment_failures:
            progress.state, progress.stop_reason = "STOPPED_ENVIRONMENT", outcome["failure_code"]
            return progress
    progress.state, progress.current = "COMPLETED", None
    return progress


def _worker(connection, root, profile):
    """자식 process: DB/S3 adapter를 한 번 만들고 받은 SHA를 하나씩 기존 경계로 처리한다."""
    from biz_aid_pipeline.config.settings import DbConfig, S3Config
    from biz_aid_pipeline.documents.repository import DocumentRepository
    from biz_aid_pipeline.parsing.orchestration import orchestrate_source
    from biz_aid_pipeline.parsing.persistence import S3ParsedArtifactStore
    from biz_aid_pipeline.parsing.repository import ParseResultRepository
    from biz_aid_pipeline.storage import S3DocumentStore
    db_config, s3_config = DbConfig.load(Path(root), profile), S3Config.load(Path(root), profile)
    sources, results = DocumentRepository(db_config), ParseResultRepository(db_config)
    source_store = S3DocumentStore(s3_config.bucket, s3_config.region, s3_config.prefix)
    artifacts = S3ParsedArtifactStore(s3_config.bucket, s3_config.region, client=source_store.client)
    while True:
        sha = connection.recv()
        if sha is None:
            break
        try:
            execution = orchestrate_source(sha, sources, source_store, results, artifacts)
            outcome = {"status": execution.status, "failure_code": execution.failure_code,
                       "action": execution.persistence_action, "parse_key": execution.parse_key,
                       "artifact_s3_key": execution.artifact_s3_key}
        except PipelineError as error:
            outcome = {"status": "EXECUTION_FAILED", "failure_code": str(error)}
        except Exception:
            # RISK: provider·DB 예외 원문은 credential을 포함할 수 있어 고정 코드만 남긴다.
            outcome = {"status": "EXECUTION_FAILED", "failure_code": "unexpected_execution_failure"}
        outcome["worker_peak_rss_mb"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // (1048576 if sys.platform == "darwin" else 1024)
        connection.send(outcome)


class Worker:
    """자식 parser process 하나. 제한 시간을 넘기거나 죽으면 종료하고 다음 source에서 새로 띄운다."""

    def __init__(self, root, profile, timeout):
        self.root, self.profile, self.timeout, self.process = root, profile, timeout, None

    def start(self):
        context = multiprocessing.get_context("spawn")
        self.connection, child = context.Pipe()
        self.process = context.Process(target=_worker, args=(child, str(self.root), self.profile), daemon=True)
        self.process.start()

    def stop(self):
        if self.process is not None:
            self.process.kill()
            self.process.join(10)
            self.process = None

    def __call__(self, sha):
        if self.process is None or not self.process.is_alive():
            self.start()
        self.connection.send(sha)
        # BOUNDARY: native parser hang은 같은 process에서 끊을 수 없어 source별 제한 시간 뒤 자식을 종료한다.
        if not self.connection.poll(self.timeout):
            self.stop()
            return {"status": "EXECUTION_FAILED", "failure_code": "source_timeout"}
        try:
            return self.connection.recv()
        except EOFError:
            self.stop()
            return {"status": "EXECUTION_FAILED", "failure_code": "worker_crashed"}

    def close(self):
        if self.process is not None and self.process.is_alive():
            self.connection.send(None)
            self.process.join(30)
        self.stop()


def run_corpus(root, profile, run_id, retry_failed=False, limit=None, max_completed=None, only=None):
    if profile != "dev":
        raise PipelineError("prod_parsing_access_forbidden")
    from biz_aid_pipeline.config.settings import DbConfig
    from biz_aid_pipeline.parsing.hwp_pdf import HwpConversionError, converter_version
    from biz_aid_pipeline.parsing.repository import ParseResultRepository
    contract = parsing_contract()
    spec = contract["corpus_execution"]
    enabled = [fmt for fmt, route in contract["routes"].items() if route["enabled"]]
    repository = ParseResultRepository(DbConfig.load(Path(root), profile))
    directory = Path(root) / RUNS / run_id
    directory.mkdir(parents=True, exist_ok=True)
    try:
        sources = select_sources(repository.verified_source_formats(), enabled)
        if only is not None:
            # 수정의 영향을 받은 source만 재처리한다. 목록에 있어도 enabled·검증된 source만 대상이다.
            sources = [source for source in sources if source[0] in only]
        sources = sources[:limit]
        try:
            hwp_version = converter_version(contract)
        except HwpConversionError:
            hwp_version = None
        keys = {}

        def key_for(sha, detected):
            route, _ = route_for(detected, contract)
            if route == "HWP_PDF_DOCLING" and hwp_version is None:
                return None
            return parse_key(sha, route, contract, hwp_version if route == "HWP_PDF_DOCLING" else None)

        def existing_status(sha, key):
            row = repository.get(sha, key)
            return row["parse_status"] if row else None

        skip = set(spec["resume_skip_statuses"]) - (set(spec["retry_statuses"]) if retry_failed else set())
        progress = Progress(run_id, len(sources), max_completed)
        results = (directory / "results.jsonl").open("a", encoding="utf-8")

        def write(sha, detected, outcome, current):
            results.write(json.dumps(dict(outcome, source_sha256=sha, detected_format=detected), ensure_ascii=False) + "\n")
            results.flush()
            snapshot = current.snapshot()
            temporary = directory / "progress.json.tmp"
            temporary.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(directory / "progress.json")

        worker = Worker(root, profile, spec["source_timeout_seconds"])
        stop = []
        # WHY: 신호로 process를 바로 끝내면 실행 중 source의 S3·DB 기록이 끊길 수 있다. 신호는 다음 source 경계의 종료 요청이다.
        for signum in (signal.SIGTERM, signal.SIGINT):
            signal.signal(signum, lambda *_: stop.append(True))
        try:
            drive(sources, key_for, existing_status, worker, progress, skip, write, spec["max_consecutive_environment_failures"],
                  max_completed, lambda: bool(stop))
        finally:
            worker.close()
            write_final(directory, progress)
            results.close()
        return progress
    finally:
        repository.close()


def write_final(directory, progress):
    temporary = directory / "progress.json.tmp"
    temporary.write_text(json.dumps(progress.snapshot(), ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(directory / "progress.json")


def status_text(root, run_id):
    snapshot = json.loads((Path(root) / RUNS / run_id / "progress.json").read_text(encoding="utf-8"))
    total, done = snapshot["total"], snapshot["completed"]
    statuses = snapshot["statuses"]
    failed = sum(count for status, count in statuses.items() if status in ("PARSE_FAILED", "CONVERSION_FAILED", "EXECUTION_FAILED"))
    elapsed = snapshot["elapsed_seconds"]
    target = snapshot.get("target", total)
    lines = [f"[Corpus Parse] {snapshot['run_id']} state={snapshot['state']}",
             f"completed: {done} / {target} ({100 * done / max(target, 1):.1f}%)  remaining: {snapshot['remaining']}"
             + (f"  (corpus total {total})" if target != total else ""),
             f"PARSED: {statuses.get('PARSED', 0)}  OCR_REQUIRED: {statuses.get('OCR_REQUIRED', 0)}  failed: {failed}  "
             f"skipped: {snapshot['skipped']}",
             f"current: {(snapshot['current'] or '-')[:12]}  elapsed: {int(elapsed // 3600)}h {int(elapsed % 3600 // 60)}m"]
    processed = snapshot["processed"]
    if processed >= 1 and snapshot["state"] == "RUNNING":
        # 이번 run에서 실제 처리한 source의 평균만 근거로 쓴다. 문서 크기·OCR 여부 분포가 달라 대략값이며 초반에는 크게 흔들린다.
        eta = (elapsed / max(done, 1)) * snapshot["remaining"]
        lines.append(f"avg/source: {elapsed / max(done, 1):.0f}s  ETA (rough, from {processed} processed): "
                     f"{int(eta // 3600)}h {int(eta % 3600 // 60)}m")
    if snapshot["stop_reason"]:
        lines.append(f"stop_reason: {snapshot['stop_reason']}")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="dev-only corpus parsing over enabled formats")
    parser.add_argument("--profile", choices=["dev"], required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--status", action="store_true", help="진행 상태만 출력")
    parser.add_argument("--retry-failed", action="store_true", help="현재 parse_key의 PARSE_FAILED·CONVERSION_FAILED도 재처리")
    parser.add_argument("--limit", type=int, help="앞에서부터 N개만(점검용)")
    parser.add_argument("--max-completed", type=int, help="완료(처리 + skip) N개에 도달하면 source 경계에서 멈춤")
    parser.add_argument("--sources-file", help="재처리할 content SHA 목록(한 줄에 하나)")
    args = parser.parse_args(argv)
    if args.status:
        print(status_text(ROOT, args.run_id))
        return 0
    only = None
    if args.sources_file:
        only = {line.strip() for line in Path(args.sources_file).read_text(encoding="utf-8").splitlines() if line.strip()}
    progress = run_corpus(ROOT, args.profile, args.run_id, args.retry_failed, args.limit, args.max_completed, only)
    print(status_text(ROOT, args.run_id))
    return 0 if progress.state in ("COMPLETED", "STOPPED_LIMIT") else 1
