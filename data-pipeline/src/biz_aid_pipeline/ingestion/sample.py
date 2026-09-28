import hashlib
from biz_aid_pipeline.bizinfo.models import SourceBatch, SourcePage, SyncScope
from biz_aid_pipeline.config.settings import ApiConfig, PipelineError, credential_echo, read_json

SAMPLE_RUN = "api-quality-dev-20260928-01"
SAMPLE_HASH = "5b4eafbed056a134c2cf1f763630ef6621030b5beb3d20921f0c5bd64a215811"


def safe_file(root, relative):
    path = root / relative
    if path.is_symlink() or path.resolve() != path or not path.is_file():
        raise PipelineError("unsafe_sample_reference")
    return path


def load_pilot_sample(root):
    reference = f"harness/workspace/artifacts/codex/phase0-api-quality/bizinfo-quality-{SAMPLE_RUN}.json"
    evidence = safe_file(root, reference)
    if hashlib.sha256(evidence.read_bytes()).hexdigest() != SAMPLE_HASH:
        raise PipelineError("pilot_sample_manifest_checksum_mismatch")
    run = read_json(evidence)["run"]
    if (run["run_id"] != SAMPLE_RUN or run["profile"] != "dev"
            or run["requested_pages"] != [1, 2, 3, 4, 5] or run["requested_rows_per_page"] != 20
            or len(run["pages"]) != 5):
        raise PipelineError("pilot_sample_plan_mismatch")
    config = ApiConfig.load(root, "dev")
    pages, hashes = [], []
    for number, entry in enumerate(run["pages"], 1):
        snapshot = f"{SAMPLE_RUN}-page{number}"
        meta_ref = f"data/raw/{snapshot}/metadata.json"
        if entry["raw_snapshot"] != meta_ref or entry["outcome"] != "SUCCESS":
            raise PipelineError("pilot_sample_page_mismatch")
        meta = read_json(safe_file(root, meta_ref))
        raw_ref = f"data/raw/{snapshot}/response.json"
        raw = safe_file(root, raw_ref).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if (meta["run_id"] != snapshot or meta["raw_path"] != "response.json"
                or digest != meta["sha256"] or digest != entry["sha256"] or len(raw) != meta["byte_count"]):
            raise PipelineError("pilot_raw_checksum_mismatch")
        if credential_echo(raw, config.key):
            raise PipelineError("credential_reflection_refused")
        payload = read_json(root / raw_ref)
        header = payload["response"]["header"]
        body = payload["response"]["body"]
        items = body["items"]["item"]
        if (header != {"resultCode": "00", "resultMsg": "NORMAL_SERVICE"}
                or body["pageNo"] != number or body["numOfRows"] != 20 or len(items) != 20
                or body["totalCount"] != entry["totalCount"]):
            raise PipelineError("pilot_raw_contract_mismatch")
        pages.append(SourcePage(number, 20, tuple(items), body["totalCount"]))
        hashes.append({"raw_reference": raw_ref, "metadata_reference": meta_ref, "sha256": digest})
    # 기존 Gate의 동일 byte만 Pilot에 사용한다. Sample이 FULL universe인 것처럼 보이게 만들지 않는다.
    return SourceBatch(SyncScope.SAMPLE, tuple(pages), "API default-order head 100", False,
        {"source_run_id": SAMPLE_RUN, "manifest": reference, "manifest_sha256": SAMPLE_HASH, "pages": hashes})
