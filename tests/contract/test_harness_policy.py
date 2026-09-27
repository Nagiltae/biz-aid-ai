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
        # Registry에서 빠진 기록도 실제 저장소처럼 복사해야 같은 누락을 테스트가 숨기지 않는다.
        files = subprocess.check_output(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT, text=True,
        ).split("\0")
        for name in filter(None, files):
            source = ROOT / name
            destination = self.directory / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination, follow_symlinks=False)
        self.git("init", "-b", "dev")
        self.git("add", "--", *filter(None, files))

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

    def test_historical_initial_review_is_complete_but_current_task_is_pending(self):
        self.update_registry(agy_review_evidence="harness/workspace/reports/agy-initial-harness-review.md")
        result = self.check("harness")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("result=pass_with_fixes", result.stdout)
        self.assertIn("CURRENT REPORT REVIEW: pending; human review PENDING", result.stdout)

    def test_targeted_review_is_complete_but_current_task_is_pending(self):
        result = self.check("harness")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("result=pass; reviewed_report=harness/workspace/reports/2026-09-27-codex-harness-fix-report.md", result.stdout)
        self.assertIn("CURRENT REPORT REVIEW: pending; human review PENDING", result.stdout)
        self.assertNotIn(self.registry["agy_review_evidence"], self.registry["required_files"])

    def add_workspace_file(self, directory, filename, tracked=True):
        name = f"harness/workspace/{directory}/{filename}"
        path = self.directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# 합성 기록\n\n회귀 테스트용 기록이며 실제 Review 판정이 아니다.\n", encoding="utf-8")
        if tracked:
            self.git("add", "--", name)
        return name

    def remove_workspace_file(self, name):
        # Commit 없는 임시 fixture에서 staged 파일을 지울 때 실제 저장소에 강제 삭제 명령을 적용하지 않는다.
        self.git("rm", "--cached", "--", name)
        (self.directory / name).unlink()

    def test_new_tracked_report_does_not_require_individual_registration(self):
        name = self.add_workspace_file("reports", "new-report.md")
        self.assertNotIn(name, self.registry["required_files"])
        for mode in ("harness", "git-tracked"):
            result = self.check(mode)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_new_tracked_checkpoint_does_not_require_individual_registration(self):
        name = self.add_workspace_file("checkpoints", "checkpoint-001.md")
        self.assertNotIn(name, self.registry["required_files"])
        for mode in ("harness", "git-tracked"):
            result = self.check(mode)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_dynamic_workspace_rejects_code_and_non_markdown_files(self):
        for directory in ("reports", "checkpoints"):
            for filename in ("malicious.py", "script.sh", "report.json"):
                with self.subTest(directory=directory, filename=filename):
                    name = self.add_workspace_file(directory, filename)
                    for mode in ("harness", "git-tracked"):
                        result = self.check(mode)
                        self.assertEqual(result.returncode, 1)
                        self.assertIn("unsafe dynamic Workspace file", result.stderr)
                    self.remove_workspace_file(name)

    def test_dynamic_workspace_rejects_symlinks(self):
        for directory in ("reports", "checkpoints"):
            with self.subTest(directory=directory):
                name = f"harness/workspace/{directory}/symlink.md"
                (self.directory / name).symlink_to(self.directory / "AGENTS.md")
                self.git("add", "--", name)
                for mode in ("harness", "git-tracked"):
                    result = self.check(mode)
                    self.assertEqual(result.returncode, 1)
                    self.assertIn("unsafe dynamic Workspace file", result.stderr)
                self.remove_workspace_file(name)

    def test_dynamic_workspace_requires_git_tracking(self):
        for directory in ("reports", "checkpoints"):
            with self.subTest(directory=directory):
                name = self.add_workspace_file(directory, "untracked.md", tracked=False)
                for mode in ("harness", "git-tracked"):
                    result = self.check(mode)
                    self.assertEqual(result.returncode, 1)
                    self.assertIn("untracked", result.stderr)
                (self.directory / name).unlink()

    def test_dynamic_workspace_cannot_be_hidden_by_ignore(self):
        path = self.directory / ".gitignore"
        original = path.read_text(encoding="utf-8")
        for directory in ("reports", "checkpoints"):
            for tracked in (True, False):
                with self.subTest(directory=directory, tracked=tracked):
                    name = self.add_workspace_file(directory, "hidden.md", tracked=tracked)
                    path.write_text(original + f"/{name}\n", encoding="utf-8")
                    self.git("add", "--", ".gitignore")
                    for mode in ("harness", "git-tracked"):
                        result = self.check(mode)
                        self.assertEqual(result.returncode, 1)
                        self.assertIn("ignored", result.stderr)
                    if tracked:
                        self.remove_workspace_file(name)
                    else:
                        (self.directory / name).unlink()
                    path.write_text(original, encoding="utf-8")
                    self.git("add", "--", ".gitignore")

    def test_unregistered_static_harness_file_still_causes_registry_drift(self):
        name = "harness/rules/random-rule.md"
        (self.directory / name).write_text("# 미등록 규칙\n", encoding="utf-8")
        self.git("add", "--", name)
        result = self.check("harness")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Registry drift", result.stderr)
        self.assertIn(name, result.stderr)

    def test_new_report_is_not_trusted_review_evidence(self):
        name = self.add_workspace_file("reports", "new-agy-review.md")
        self.update_registry(agy_review_evidence=name)
        result = self.check("harness")
        self.assertEqual(result.returncode, 1)
        self.assertIn("independent evidence must be user-acknowledged", result.stderr)
        self.update_registry(agy_review="pending", agy_review_evidence=None)
        result = self.check("harness")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PENDING: independent AGY review", result.stdout)

    def test_dynamic_workspace_path_policy_cannot_expand_to_static_files(self):
        self.update_registry(dynamic_paths=[*self.registry["dynamic_paths"], "harness/rules/*.md"])
        result = self.check("harness")
        self.assertEqual(result.returncode, 1)
        self.assertIn("dynamic Workspace path policy drift", result.stderr)

    def test_dynamic_workspace_rejects_nested_files_and_executable_markdown(self):
        for directory in ("reports", "checkpoints"):
            for filename in ("nested/report.md", "executable.md"):
                with self.subTest(directory=directory, filename=filename):
                    name = self.add_workspace_file(directory, filename)
                    path = self.directory / name
                    if filename == "executable.md":
                        path.chmod(0o755)
                        self.git("add", "--", name)
                    result = self.check("harness")
                    self.assertEqual(result.returncode, 1)
                    self.assertIn("unsafe dynamic Workspace file", result.stderr)
                    self.remove_workspace_file(name)
                    if filename.startswith("nested/"):
                        path.parent.rmdir()

    def test_fixed_checkpoint_readme_remains_required(self):
        name = "harness/workspace/checkpoints/README.md"
        self.assertIn(name, self.registry["required_files"])
        self.remove_workspace_file(name)
        result = self.check("harness")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Registry drift", result.stderr)
        self.assertIn(name, result.stderr)

    def test_dynamic_report_must_not_be_individually_registered(self):
        name = self.add_workspace_file("reports", "new-report.md")
        self.update_registry(required_files=sorted([*self.registry["required_files"], name]))
        result = self.check("harness")
        self.assertEqual(result.returncode, 1)
        self.assertIn("must not be individually registered", result.stderr)

    def test_artifacts_cannot_hide_code_rules_or_final_reports(self):
        path = self.directory / ".gitignore"
        original = path.read_text(encoding="utf-8")
        for filename in ("final-report.md", "code.py", "script.sh"):
            with self.subTest(filename=filename):
                name = f"harness/workspace/artifacts/{filename}"
                path.write_text(original + f"/{name}\n", encoding="utf-8")
                (self.directory / name).write_text("금지된 숨김 결과\n", encoding="utf-8")
                self.git("add", "--", ".gitignore")
                result = self.check("git-tracked")
                self.assertEqual(result.returncode, 1)
                self.assertIn("ignored project result", result.stderr)
                (self.directory / name).unlink()
        path.write_text(original, encoding="utf-8")

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
        self.assertIn("unsafe dynamic Workspace file", result.stderr)

    def test_forged_complete_heading_cannot_replace_independent_review(self):
        path = self.directory / self.registry["agy_review_evidence"]
        path.write_text("# AGY Initial Harness Review\n\n**Reviewer**: AGY\n\n## PASS\n\nReview Status: COMPLETE\n", encoding="utf-8")
        result = self.check("harness")
        self.assertEqual(result.returncode, 1)
        self.assertIn("checksum mismatch", result.stderr)

    def test_review_basis_report_change_invalidates_the_evidence(self):
        path = self.directory / "harness/workspace/reports/2026-09-27-codex-harness-fix-report.md"
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
        self.assertIn("unsafe dynamic Workspace file", result.stderr)

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

    def test_profile_secrets_are_ignored_and_example_is_tracked(self):
        result = subprocess.run(
            ["git", "check-ignore", "--no-index", ".env.dev", ".env.prod"],
            cwd=self.directory, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(set(result.stdout.splitlines()), {".env.dev", ".env.prod"})
        ignored = subprocess.run(["git", "check-ignore", "--no-index", ".env.example"],
                                 cwd=self.directory, capture_output=True, text=True)
        self.assertEqual(ignored.returncode, 1)
        tracked = subprocess.check_output(["git", "ls-files", ".env.example"], cwd=self.directory, text=True)
        self.assertEqual(tracked.strip(), ".env.example")

    def test_tracked_profile_secret_file_is_rejected(self):
        # 실제 사용자 Secret은 복사하지 않고 격리된 Git fixture의 합성 설정으로만 추적 오류를 재현한다.
        for name in (".env.dev", ".env.prod"):
            with self.subTest(name=name):
                path = self.directory / name
                path.write_text("BIZINFO_SERVICE_KEY=synthetic-fixture-key\n", encoding="utf-8")
                self.git("add", "-f", "--", name)
                result = self.check("git-tracked")
                self.assertEqual(result.returncode, 1)
                self.assertIn("raw/secret/cache must not be tracked", result.stderr)
                self.git("rm", "--cached", "--", name)
                path.unlink()

    def test_ignored_env_example_is_rejected(self):
        path = self.directory / ".gitignore"
        path.write_text(path.read_text(encoding="utf-8") + "\n.env.example\n", encoding="utf-8")
        self.git("add", "--", ".gitignore")
        result = self.check("git-tracked")
        self.assertEqual(result.returncode, 1)
        self.assertIn("required files are ignored", result.stderr)

    def test_profile_ignore_policy_is_required_even_without_secret_files(self):
        path = self.directory / ".gitignore"
        path.write_text(path.read_text(encoding="utf-8").replace(".env.*\n", ".env.dev\n"), encoding="utf-8")
        self.git("add", "--", ".gitignore")
        result = self.check("git-tracked")
        self.assertEqual(result.returncode, 1)
        self.assertIn("profile secret files must be ignored", result.stderr)

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
