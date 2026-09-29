import copy
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data-pipeline/src"))

from biz_aid_pipeline.config.settings import PipelineError
from biz_aid_pipeline.parsing import provisioning
from biz_aid_pipeline.parsing.models import (artifact_files, artifacts_cache_key, artifacts_manifest_sha256,
                                             model_artifacts_sha256, parsing_contract)

ENV = "BIZAID_DOCLING_ARTIFACTS_PATH"


def content(folder, name):
    return f"{folder}/{name}".encode()


class DoclingProvisioningContractTests(unittest.TestCase):
    def setUp(self):
        artifacts_manifest_sha256.cache_clear()
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.addCleanup(artifacts_manifest_sha256.cache_clear)
        self.contract = copy.deepcopy(parsing_contract())
        # 실제 506 MB 모델 대신 같은 파일 목록 구조의 작은 합성 artifact로 identity 경계를 검증한다.
        reference = Path(self.directory.name) / "reference"
        self.write(reference)
        self.contract["dependencies"]["docling"]["model_artifacts"]["expected_manifest_sha256"] = (
            artifacts_manifest_sha256(str(reference), artifact_files(self.contract)))
        artifacts_manifest_sha256.cache_clear()
        self.target = Path(self.directory.name) / "artifacts"

    def write(self, root, override=None):
        for folder, name in artifact_files(self.contract):
            path = Path(root) / folder / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((override or {}).get((folder, name), content(folder, name)))

    def fake_download(self, override=None, fail_after=None):
        calls = []

        def download(repo_id, filename, revision, local_dir):
            calls.append((repo_id, filename, revision))
            if fail_after is not None and len(calls) > fail_after:
                raise OSError("network interrupted")
            folder = Path(local_dir).name
            path = Path(local_dir) / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((override or {}).get((folder, filename), content(folder, filename)))
            return str(path)
        return download, calls

    def test_contract_pins_resolved_commits_and_explicit_file_lists(self):
        spec = parsing_contract()["dependencies"]["docling"]["model_artifacts"]
        for model in spec["models"]:
            self.assertRegex(model["resolved_snapshot"], r"^[0-9a-f]{40}$")
            self.assertTrue(model["files"])
        self.assertRegex(spec["expected_manifest_sha256"], r"^[0-9a-f]{64}$")
        # production 표 engine은 PP-TableMagic이므로 TableFormer 가중치는 artifact identity에 없다.
        repos = {model["repo_id"] for model in spec["models"]}
        self.assertNotIn("docling-project/docling-models", repos)
        self.assertIn("docling-project/docling-layout-heron", repos)
        self.assertEqual(sum(repo.startswith("PaddlePaddle/") for repo in repos), 6)

    def test_cache_key_changes_only_with_model_identity(self):
        key = artifacts_cache_key(self.contract)
        self.assertRegex(key, r"^docling-artifacts-v1(-[0-9a-f]{12})+-[0-9a-f]{16}$")
        unrelated = copy.deepcopy(self.contract)
        unrelated["routes"]["XLSX"]["approved_direction"] = "문서 수정"
        unrelated["versioning"]["normalizer_version"] += 1
        self.assertEqual(key, artifacts_cache_key(unrelated))
        for change in ("revision", "files", "manifest", "schema"):
            changed = copy.deepcopy(self.contract)
            spec = changed["dependencies"]["docling"]["model_artifacts"]
            if change == "revision":
                spec["models"][1]["resolved_snapshot"] = "0" * 40
            elif change == "files":
                spec["models"][1]["files"] = spec["models"][1]["files"][:-1]
            elif change == "manifest":
                spec["expected_manifest_sha256"] = "1" * 64
            else:
                spec["cache_key_schema"] += 1
            with self.subTest(change=change):
                self.assertNotEqual(key, artifacts_cache_key(changed))

    def test_verify_requires_complete_matching_artifacts(self):
        with mock.patch.dict(os.environ, {ENV: str(self.target)}):
            with self.assertRaisesRegex(PipelineError, "docling_artifacts_missing"):
                provisioning.verify(self.contract)
            self.write(self.target)
            expected = self.contract["dependencies"]["docling"]["model_artifacts"]["expected_manifest_sha256"]
            self.assertEqual(provisioning.verify(self.contract), expected)
            folder, name = artifact_files(self.contract)[0]
            (self.target / folder / name).write_bytes(b"corrupted cache")
            artifacts_manifest_sha256.cache_clear()
            with self.assertRaisesRegex(PipelineError, "docling_artifacts_identity_mismatch"):
                model_artifacts_sha256(self.contract)

    def test_provision_downloads_resolved_commits_then_moves_verified_artifacts(self):
        download, calls = self.fake_download()
        with mock.patch.dict(os.environ, {ENV: str(self.target)}), mock.patch("huggingface_hub.hf_hub_download", download):
            actual = provisioning.provision(self.contract, allow_network=True)
        spec = self.contract["dependencies"]["docling"]["model_artifacts"]
        self.assertEqual(actual, spec["expected_manifest_sha256"])
        revisions = {model["repo_id"]: model["resolved_snapshot"] for model in spec["models"]}
        self.assertEqual(len(calls), len(artifact_files(self.contract)))
        for repo_id, _, revision in calls:
            # tag 이름이 아니라 Contract의 commit으로만 받는다.
            self.assertEqual(revision, revisions[repo_id])
        self.assertFalse((self.target.parent / "artifacts.staging").exists())
        with mock.patch.dict(os.environ, {ENV: str(self.target)}), mock.patch("huggingface_hub.hf_hub_download") as again:
            self.assertEqual(provisioning.provision(self.contract, allow_network=True), actual)
            again.assert_not_called()

    def test_incomplete_or_corrupt_download_never_lands(self):
        folder, name = artifact_files(self.contract)[-1]
        for label, download in (("corrupt", self.fake_download({(folder, name): b"tampered"})[0]),
                                ("interrupted", self.fake_download(fail_after=2)[0])):
            with self.subTest(case=label), mock.patch.dict(os.environ, {ENV: str(self.target)}), \
                    mock.patch("huggingface_hub.hf_hub_download", download):
                with self.assertRaises((PipelineError, OSError)):
                    provisioning.provision(self.contract, allow_network=True)
                self.assertFalse(any((self.target / model).exists() for model, _ in artifact_files(self.contract)))

    def test_provision_requires_explicit_network_and_keeps_existing_mismatch(self):
        with mock.patch.dict(os.environ, {ENV: str(self.target)}), mock.patch("huggingface_hub.hf_hub_download") as download:
            with self.assertRaisesRegex(PipelineError, "provisioning_requires_allow_network"):
                provisioning.provision(self.contract, allow_network=False)
            folder, name = artifact_files(self.contract)[0]
            (self.target / folder).mkdir(parents=True)
            (self.target / folder / name).write_bytes(b"partial")
            with self.assertRaisesRegex(PipelineError, "incomplete_artifacts_present"):
                provisioning.provision(self.contract, allow_network=True)
            download.assert_not_called()
            self.assertEqual((self.target / folder / name).read_bytes(), b"partial")

    def test_ci_separates_network_provisioning_from_offline_validation(self):
        workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
        steps = workflow["jobs"]["validate"]["steps"]
        names = [step.get("name", step.get("uses", "")) for step in steps]
        order = ["Resolve Docling artifact location and cache key", "Restore Docling artifacts",
                 "Provision Docling artifacts (network, cache miss only)", "Verify Docling artifacts identity",
                 "Save Docling artifacts", "Check current environment", "Validate current scope"]
        self.assertEqual([name for name in names if name in order], order)
        step = {name: item for name, item in zip(names, steps)}
        self.assertIn("provision_docling_artifacts.py cache-key", step[order[0]]["run"])
        self.assertIn("docling-artifacts", step[order[0]]["run"])
        self.assertEqual(step[order[1]]["uses"], "actions/cache/restore@v4")
        self.assertEqual(step[order[4]]["uses"], "actions/cache/save@v4")
        for name in (order[2], order[4]):
            self.assertEqual(step[name]["if"], "steps.docling-cache.outputs.cache-hit != 'true'")
        self.assertEqual(step[order[2]]["env"]["HF_HUB_OFFLINE"], "0")
        for name in (order[3], order[5], order[6]):
            self.assertEqual(step[name]["env"]["HF_HUB_OFFLINE"], "1")
            self.assertNotIn("if", step[name])
        runs = "\n".join(item.get("run", "") for item in steps)
        self.assertEqual(runs.count("--allow-network"), 1)
        self.assertIsNone(re.search(r"unittest.*(-k|skip)|SKIP_PDF", runs))


if __name__ == "__main__":
    unittest.main()
