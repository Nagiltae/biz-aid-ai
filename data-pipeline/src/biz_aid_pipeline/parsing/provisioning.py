import argparse
import hashlib
import os
import shutil
import sys
from pathlib import Path

from biz_aid_pipeline.config.settings import PipelineError
from biz_aid_pipeline.parsing.models import (artifact_files, artifacts_cache_key, artifacts_manifest_sha256,
                                             docling_artifacts_path, model_artifacts_sha256, parsing_contract)


def target_path(contract):
    name = contract["dependencies"]["docling"]["model_artifacts"]["artifacts_path_env"]
    value = os.environ.get(name, "").strip()
    if not value:
        raise PipelineError("docling_artifacts_path_required:" + name)
    return Path(value).expanduser().resolve()


def union_manifest_sha256(contract, target, staging, complete):
    """기존 완전 폴더는 target에서, 새 폴더는 staging에서 읽어 models.artifacts_manifest_sha256과 같은 규칙으로 계산한다."""
    digest = hashlib.sha256()
    for folder, name in sorted(artifact_files(contract)):
        with ((target if folder in complete else staging) / folder / name).open("rb") as stream:
            digest.update(f"{folder}/{name}\0{hashlib.file_digest(stream, 'sha256').hexdigest()}\n".encode())
    return digest.hexdigest()


def verify(contract):
    return model_artifacts_sha256(contract)


def provision(contract, allow_network):
    # BOUNDARY: 네트워크는 이 명시적 provisioning 명령에서만 쓰고 parser·test runtime은 준비된 artifact만 읽는다.
    if not allow_network:
        raise PipelineError("provisioning_requires_allow_network")
    target = target_path(contract)
    spec = contract["dependencies"]["docling"]["model_artifacts"]
    try:
        return verify(contract)
    except PipelineError as error:
        if not str(error).startswith("docling_artifacts_missing"):
            # EXCEPTION: 존재하지만 identity가 다른 artifact는 사람이 확인해야 하므로 덮어쓰거나 지우지 않는다.
            raise
    # 모든 파일이 있는 모델 폴더는 두고, 없는 모델 폴더만 받는다. 일부만 있는 폴더는 사람이 확인해야 한다.
    complete = {model["folder"] for model in spec["models"]
                if all((target / model["folder"] / name).is_file() for name in model["files"])}
    partial = [model["folder"] for model in spec["models"]
               if model["folder"] not in complete and (target / model["folder"]).exists()]
    if partial:
        raise PipelineError("incomplete_artifacts_present:" + ",".join(partial))
    missing = [model for model in spec["models"] if model["folder"] not in complete]
    staging = target.parent / (target.name + ".staging")
    if staging.exists():
        shutil.rmtree(staging)
    os.environ["HF_HUB_OFFLINE"] = "0"
    from huggingface_hub import hf_hub_download
    try:
        for model in missing:
            for name in model["files"]:
                # tag가 아니라 해석된 commit으로 받아 같은 이름의 다른 가중치가 섞이지 않게 한다.
                hf_hub_download(repo_id=model["repo_id"], filename=name, revision=model["resolved_snapshot"],
                                local_dir=staging / model["folder"])
        # RISK: 새로 받은 파일과 기존 파일을 합친 identity가 기대값과 같을 때만 옮긴다. 다르면 기존 artifact를 건드리지 않는다.
        if union_manifest_sha256(contract, target, staging, complete) != spec["expected_manifest_sha256"]:
            raise PipelineError("provisioned_artifacts_identity_mismatch")
        target.mkdir(parents=True, exist_ok=True)
        for model in missing:
            (staging / model["folder"]).rename(target / model["folder"])
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    artifacts_manifest_sha256.cache_clear()
    docling_artifacts_path(contract)
    return verify(contract)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Docling 모델 artifact의 cache key 계산·검증·명시적 provisioning")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("cache-key")
    commands.add_parser("verify")
    provision_parser = commands.add_parser("provision")
    provision_parser.add_argument("--allow-network", action="store_true")
    args = parser.parse_args(argv)
    contract = parsing_contract()
    try:
        if args.command == "cache-key":
            print(artifacts_cache_key(contract))
        elif args.command == "verify":
            print("PASS: docling artifacts identity " + verify(contract))
        else:
            print("PASS: docling artifacts provisioned " + provision(contract, args.allow_network))
    except PipelineError as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    return 0
