import hashlib
import json
import re
from dataclasses import asdict
from pathlib import Path

from biz_aid_pipeline.bizinfo.client import BizinfoClient
from biz_aid_pipeline.bizinfo.models import SourceBatch, SourcePage, SyncScope
from biz_aid_pipeline.config.settings import ApiConfig, PipelineError, api_contract, credential_echo, read_json
from biz_aid_pipeline.quality.structured_data_gate import now


def valid_run_id(identifier):
    if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", identifier):
        raise PipelineError("invalid_full_run_id")


def safe_path(root, relative):
    path = root / relative
    if path.resolve() != path or path.is_symlink() or not path.is_relative_to(root):
        raise PipelineError("unsafe_full_evidence_path")
    return path


def write_json_new(root, path, value, secrets=()):
    raw = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()
    if any(credential_echo(raw, secret) for secret in secrets if secret):
        raise PipelineError("credential_reflection_refused")
    safe_path(root, path.relative_to(root))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)


class FullSnapshots:
    def __init__(self, root, identifier, key, evidence_kind):
        valid_run_id(identifier)
        self.root, self.identifier, self.key = Path(root).resolve(), identifier, key
        self.directory = safe_path(self.root, f"data/raw/{identifier}")
        self.directory.parent.mkdir(parents=True, exist_ok=True)
        self.directory.mkdir(exist_ok=False)
        self.entries, self.pending = [], {}
        self.started_at, self.evidence_kind = now(), evidence_kind
        self.max_bytes = api_contract(self.root)["probe"]["max_response_bytes"]
        self.checkpoint_sequence = 0
        self.checkpoint("ACQUISITION", 1, 0, 0, "첫 페이지에서 실행 시점 totalCount를 확인한다")

    def checkpoint(self, stage, target, completed, failed, next_action, resume_command=None):
        value = {"run_id": self.identifier, "task": "Phase 1B Full Structured Data Sync",
                 "started_at": self.started_at, "updated_at": now(), "total_target": target,
                 "completed_count": completed, "failed_count": failed,
                 "failed_items": [{"item_id": page["number"], "stage": "ACQUISITION", "reason": page["outcome"],
                                   "attempts": 1, "evidence": page["raw_snapshot"]}
                                  for page in self.entries if page["outcome"] != "SUCCESS"],
                 "current_stage": stage, "last_processed_item": self.entries[-1]["number"] if self.entries else None,
                 "next_action": next_action, "resume_command": resume_command,
                 "notes": ["집계 단위는 API 응답 계약을 확인한 페이지다. FULL 완전성이나 DB 성공을 의미하지 않는다.",
                           "중단된 pagination을 이어 받아 다른 시점의 API universe와 혼합하지 않는다. 재수집은 새 run-id를 사용한다."],
                 "status": "blocked" if failed or resume_command else "running"}
        raw = ("# FULL 수집 Checkpoint\n\n```json\n" + json.dumps(value, ensure_ascii=False, indent=2) + "\n```\n").encode()
        if credential_echo(raw, self.key):
            raise PipelineError("credential_reflection_refused")
        path = safe_path(self.root, f"harness/workspace/checkpoints/{self.identifier}-full-{self.checkpoint_sequence:04d}.md")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(raw)
        self.checkpoint_sequence += 1

    def preserve(self, number, rows, status, raw):
        # Client에서도 반사를 검사하지만 원문 저장 경계 자체가 credential 유출을 거부해야 한다.
        if credential_echo(raw, self.key) or len(raw) > self.max_bytes:
            raise PipelineError("credential_reflection_refused")
        directory = self.directory / f"page-{number:06d}"
        directory.mkdir(exist_ok=False)
        with (directory / "response.json").open("xb") as stream:
            stream.write(raw)
        try:
            read_json(directory / "response.json")
            syntax = "valid"
        except (ValueError, UnicodeError):
            syntax = "invalid"
        digest = hashlib.sha256(raw).hexdigest()
        meta = {"version": 1, "source": "bizinfo", "run_id": f"{self.identifier}-page{number}",
                "collected_at": now(), "preserved_at": now(), "payload_syntax": syntax,
                "media_type": "application/json", "raw_path": "response.json", "sha256": digest,
                "byte_count": len(raw), "http_status": status,
                "request": {"dataType": "json", "pageNo": number, "numOfRows": rows}}
        path = directory / "metadata.json"
        write_json_new(self.root, path, meta, (self.key,))
        self.pending[number] = {"metadata": str(path.relative_to(self.root)), "sha256": digest,
                                "metadata_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    def page_completed(self, page):
        entry = asdict(page)
        entry.pop("items")
        entry["item_count"] = len(page.items)
        entry["raw_snapshot"] = self.pending.pop(page.number, None)
        self.entries.append(entry)
        first = self.entries[0]
        target = max(1, (first["total_count"] + first["requested_rows"] - 1) // first["requested_rows"]) if first["outcome"] == "SUCCESS" else 1
        completed = sum(item["outcome"] == "SUCCESS" for item in self.entries)
        self.checkpoint("ACQUISITION", target, completed, len(self.entries) - completed,
                        "남은 페이지를 순차 수집한다" if len(self.entries) < target and page.outcome == "SUCCESS" else "저장된 snapshot 완전성을 검증한다")

    def finish(self, batch):
        manifest = {"version": 1, "run_id": self.identifier, "profile": "dev", "scope": "FULL",
                    "evidence_kind": self.evidence_kind, "started_at": self.started_at, "finished_at": now(),
                    "pagination_terminated": batch.pagination_terminated, "pages": self.entries}
        path = self.directory / "manifest.json"
        write_json_new(self.root, path, manifest, (self.key,))
        return {"manifest": str(path.relative_to(self.root)), "manifest_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "kind": self.evidence_kind, "official_ordering": "UNCONFIRMED",
                "acquisition_started_at": self.started_at, "acquisition_finished_at": manifest["finished_at"]}


def verify_full_snapshot(root, identifier, provenance, key=""):
    root = Path(root).resolve()
    valid_run_id(identifier)
    relative = f"data/raw/{identifier}/manifest.json"
    manifest_path = safe_path(root, relative)
    if (provenance["manifest"] != relative or hashlib.sha256(manifest_path.read_bytes()).hexdigest() != provenance["manifest_sha256"]):
        raise PipelineError("full_manifest_checksum_mismatch")
    manifest = read_json(manifest_path)
    if manifest["run_id"] != identifier or manifest["profile"] != "dev" or manifest["scope"] != "FULL":
        raise PipelineError("full_manifest_identity_mismatch")
    pages = []
    endpoint = api_contract(root)["request"]["endpoint"]
    for number, entry in enumerate(manifest["pages"], 1):
        if entry["number"] != number:
            raise PipelineError("full_snapshot_page_sequence")
        snapshot = entry["raw_snapshot"]
        if snapshot is None:
            if entry["outcome"] not in ("TRANSPORT_ERROR", "CONTRACT_ERROR") or entry["item_count"]:
                raise PipelineError("full_snapshot_missing_raw")
            pages.append(SourcePage(number, entry["requested_rows"], (), entry["total_count"], entry["outcome"],
                                    entry["http_status"], entry["result_code"], entry["result_message"], entry["echo_matches"]))
            continue
        expected = f"data/raw/{identifier}/page-{number:06d}/metadata.json"
        if snapshot["metadata"] != expected:
            raise PipelineError("full_snapshot_reference_mismatch")
        path = safe_path(root, expected)
        if hashlib.sha256(path.read_bytes()).hexdigest() != snapshot["metadata_sha256"]:
            raise PipelineError("full_snapshot_metadata_checksum_mismatch")
        meta = read_json(path)
        raw = safe_path(root, str(path.parent.relative_to(root) / "response.json")).read_bytes()
        if (meta["run_id"] != f"{identifier}-page{number}" or meta["raw_path"] != "response.json"
                or meta["request"] != {"dataType": "json", "pageNo": number, "numOfRows": entry["requested_rows"]}
                or meta["http_status"] != entry["http_status"] or len(raw) != meta["byte_count"]
                or hashlib.sha256(raw).hexdigest() != meta["sha256"] or meta["sha256"] != snapshot["sha256"]
                or credential_echo(raw, key)):
            raise PipelineError("full_snapshot_checksum_or_metadata_mismatch")
        # 저장 원문을 동일한 Client 계약으로 다시 검증한다. transport는 로컬 byte를 반환하며 HTTP를 호출하지 않는다.
        client = BizinfoClient(ApiConfig("dev", endpoint, key or "offline-snapshot-verification"), root,
                              transport=lambda url: (entry["http_status"], raw))
        page = client.fetch_page(number, entry["requested_rows"])
        actual = asdict(page)
        actual.pop("items")
        if any(actual[k] != entry[k] for k in actual) or len(page.items) != entry["item_count"]:
            raise PipelineError("full_snapshot_contract_result_mismatch")
        pages.append(page)
    return SourceBatch(SyncScope.FULL, tuple(pages), "API FULL at acquisition time", manifest["pagination_terminated"], provenance)
