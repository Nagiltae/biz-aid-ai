import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class HarnessPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.registry = json.loads((ROOT / "harness/registry.json").read_text(encoding="utf-8"))
        for name in self.registry["required_files"]:
            source = ROOT / name
            destination = self.directory / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        self.git("init", "-b", "dev")
        self.git("add", "--", *self.registry["required_files"])

    def git(self, *args):
        result = subprocess.run(["git", *args], cwd=self.directory, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def check(self, mode):
        return subprocess.run(
            ["bash", str(self.directory / f"scripts/check-{mode}.sh")],
            cwd=self.directory, capture_output=True, text=True,
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
        )

    def test_registered_repository_is_valid(self):
        for mode in ("harness", "git-tracked", "comments"):
            with self.subTest(mode=mode):
                result = self.check(mode)
                self.assertEqual(result.returncode, 0, result.stderr)

    def update_registry(self, **changes):
        self.registry.update(changes)
        (self.directory / "harness/registry.json").write_text(
            json.dumps(self.registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
        )

    def test_independent_initial_review_is_complete_but_current_fixes_are_pending(self):
        result = self.check("harness")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("result=pass_with_fixes", result.stdout)
        self.assertIn("CURRENT REPORT REVIEW: pending; human review PENDING", result.stdout)

    def test_pending_without_evidence_is_valid_for_a_new_review_cycle(self):
        self.update_registry(agy_review="pending", agy_review_evidence=None)
        result = self.check("harness")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PENDING: independent AGY review of current report", result.stdout)

    def test_pending_cannot_claim_completed_evidence(self):
        self.update_registry(agy_review="pending")
        result = self.check("harness")
        self.assertEqual(result.returncode, 1)
        self.assertIn("pending requires null evidence", result.stderr)

    def test_unknown_review_state_is_rejected(self):
        self.update_registry(agy_review="approved_by_codex")
        result = self.check("harness")
        self.assertEqual(result.returncode, 1)
        self.assertIn("unsupported lifecycle state", result.stderr)

    def test_complete_without_evidence_is_rejected(self):
        self.update_registry(agy_review_evidence=None)
        result = self.check("harness")
        self.assertEqual(result.returncode, 1)
        self.assertIn("independent evidence must be user-acknowledged", result.stderr)

    def test_codex_report_cannot_be_independent_review_evidence(self):
        self.update_registry(agy_review_evidence=self.registry["report"])
        result = self.check("harness")
        self.assertEqual(result.returncode, 1)
        self.assertIn("independent evidence must be user-acknowledged", result.stderr)

    def test_missing_independent_review_is_rejected(self):
        (self.directory / self.registry["agy_review_evidence"]).unlink()
        result = self.check("harness")
        self.assertEqual(result.returncode, 1)
        self.assertIn("missing or unsafe evidence/basis", result.stderr)

    def test_forged_complete_heading_cannot_replace_independent_review(self):
        path = self.directory / self.registry["agy_review_evidence"]
        path.write_text("# AGY Initial Harness Review\n\n**Reviewer**: AGY\n\n## PASS\n\nReview Status: COMPLETE\n", encoding="utf-8")
        result = self.check("harness")
        self.assertEqual(result.returncode, 1)
        self.assertIn("checksum mismatch", result.stderr)

    def test_review_basis_report_change_invalidates_the_evidence(self):
        path = self.directory / "harness/workspace/reports/2026-09-27-codex-harness-report.md"
        path.write_text(path.read_text(encoding="utf-8") + "\n변경된 검토 대상\n", encoding="utf-8")
        result = self.check("harness")
        self.assertEqual(result.returncode, 1)
        self.assertIn("evidence/basis checksum mismatch", result.stderr)

    def test_external_symlink_cannot_replace_independent_review(self):
        path = self.directory / self.registry["agy_review_evidence"]
        path.unlink()
        path.symlink_to(ROOT / self.registry["agy_review_evidence"])
        result = self.check("harness")
        self.assertEqual(result.returncode, 1)
        self.assertIn("missing or unsafe evidence/basis", result.stderr)

    def test_stale_registry_report_cannot_approve_the_current_task(self):
        self.update_registry(report="harness/workspace/reports/2026-09-27-codex-harness-report.md")
        result = self.check("harness")
        self.assertEqual(result.returncode, 1)
        self.assertIn("current-task Final Report differs", result.stderr)

    def test_ide_metadata_is_ignored_but_code_and_reports_cannot_be_hidden(self):
        directory = self.directory / ".idea"
        directory.mkdir()
        (directory / "workspace.xml").write_text("<project/>", encoding="utf-8")
        (directory / "biz-aid-ai.iml").write_text("<module/>", encoding="utf-8")
        result = self.check("git-tracked")
        self.assertEqual(result.returncode, 0, result.stderr)
        for name in ("hidden.md", "hidden.py"):
            with self.subTest(name=name):
                path = directory / name
                path.write_text("hidden\n", encoding="utf-8")
                result = self.check("git-tracked")
                self.assertEqual(result.returncode, 1)
                self.assertIn("ignored project result", result.stderr)
                path.unlink()

    def test_broken_context_link_is_detected(self):
        path = self.directory / "AGENTS.md"
        path.write_text(path.read_text(encoding="utf-8") + "\n[실패 링크](harness/docs/missing.md)\n", encoding="utf-8")
        result = self.check("harness")
        self.assertEqual(result.returncode, 1)
        self.assertIn("broken/outside", result.stderr)

    def test_untracked_project_file_is_detected(self):
        (self.directory / "forgotten.md").write_text("# 누락\n", encoding="utf-8")
        result = self.check("git-tracked")
        self.assertEqual(result.returncode, 1)
        self.assertIn("untracked", result.stderr)

    def test_ignored_result_cannot_be_hidden(self):
        path = self.directory / ".gitignore"
        path.write_text(path.read_text(encoding="utf-8") + "/harness/docs/hidden.md\n", encoding="utf-8")
        (self.directory / "harness/docs/hidden.md").write_text("# 숨긴 결과\n", encoding="utf-8")
        self.git("add", "--", ".gitignore")
        result = self.check("git-tracked")
        self.assertEqual(result.returncode, 1)
        self.assertIn("ignored project result", result.stderr)

    def test_wrong_branch_is_rejected(self):
        self.git("symbolic-ref", "HEAD", "refs/heads/main")
        result = self.check("git-tracked")
        self.assertEqual(result.returncode, 1)
        self.assertIn("must be on dev", result.stderr)

    def test_unimplemented_module_cannot_be_silently_added(self):
        (self.directory / "frontend").mkdir()
        result = self.check("harness")
        self.assertEqual(result.returncode, 1)
        self.assertIn("product module added", result.stderr)

    def test_ci_branch_drift_is_detected(self):
        path = self.directory / ".github/workflows/ci.yml"
        path.write_text(path.read_text(encoding="utf-8").replace("branches: [dev]", "branches: [op]"), encoding="utf-8")
        result = self.check("harness")
        self.assertEqual(result.returncode, 1)
        self.assertIn("CI must enforce dev", result.stderr)

    def test_english_explanatory_comment_is_rejected(self):
        path = self.directory / "scripts/phase0.py"
        path.write_text(path.read_text(encoding="utf-8") + "\n# explanatory English comment\n", encoding="utf-8")
        result = self.check("comments")
        self.assertEqual(result.returncode, 1)
        self.assertIn("requires Korean", result.stderr)

    def test_failure_is_not_masked_by_later_success(self):
        directory = self.directory / "orchestrator"
        directory.mkdir()
        shutil.copy2(ROOT / "scripts/check-all.sh", directory / "check-all.sh")
        for name in ("setup", "check-format", "check-lint", "check-contract", "check-integration",
                     "check-git-tracked", "check-comments", "check-harness"):
            path = directory / f"{name}.sh"
            path.write_text("#!/usr/bin/env bash\nexit " + ("1" if name == "check-contract" else "0") + "\n", encoding="utf-8")
            path.chmod(0o755)
        result = subprocess.run(["bash", str(directory / "check-all.sh")], cwd=directory, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("one or more applicable validations failed", result.stderr)
        self.assertIn("RUN: check-harness.sh", result.stdout)


if __name__ == "__main__":
    unittest.main()
