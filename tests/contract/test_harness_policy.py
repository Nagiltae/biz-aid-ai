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
        self.git("add", "-f", "--", *filter(None, files))

    def git(self, *args):
        result = subprocess.run(["git", *args], cwd=self.directory, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def check(self, mode):
        return subprocess.run(
            ["bash", str(self.directory / f"scripts/check-{mode}.sh")],
            cwd=self.directory, capture_output=True, text=True,
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
        )

    def test_registered_regression_runner_is_strict_not_generated(self):
        path = self.directory / "harness/workspace/artifacts/development/regression-set/run.py"
        original = path.read_bytes()
        path.write_bytes(original + b"invalid whitespace  ")
        self.assertEqual(self.check("format").returncode, 1)
        path.unlink()
        self.assertEqual(self.check("harness").returncode, 1)

    def test_user_handoff_output_is_narrow_and_non_gating(self):
        path = self.directory / "harness/workspace/handoff/bundle1-handoff.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("handoff output  ")
        (path.parent / "bundle2-handoff.md").write_text("second task handoff  ")
        (path.parent / "bundle4-handoff.md").write_text("bundle4 handoff  ")
        (path.parent / "bundle6-0-handoff.md").write_text("deployment kit handoff  ")
        for mode in ("format", "harness", "git-tracked"):
            self.assertEqual(self.check(mode).returncode, 0)
        (path.parent / "unregistered-control.md").write_text("not a generated checkpoint\n")
        self.assertEqual(self.check("git-tracked").returncode, 1)

    def test_registered_repository_is_valid(self):
        for mode in ("harness", "git-tracked", "comments"):
            with self.subTest(mode=mode):
                result = self.check(mode)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_agent_task_outputs_are_non_gating_untracked_and_ignored(self):
        directories = (
            "reports/development",
            "reports/codex",
            "reports/claude",
            "reports/agy",
            "artifacts/development/synthetic-task/logs",
            "artifacts/codex/synthetic-task/logs",
            "artifacts/claude/synthetic-task/logs",
            "artifacts/agy/synthetic-review",
        )
        for ignored in (True, False):
            with self.subTest(ignored=ignored):
                if not ignored:
                    path = self.directory / ".gitignore"
                    path.write_text("\n".join(line for line in path.read_text().splitlines()
                        if not line.startswith(("/harness/workspace/reports/", "/harness/workspace/artifacts/"))) + "\n")
                    self.git("add", "--", ".gitignore")
                for directory in directories:
                    suffix = ".md" if directory.startswith("reports/") else ".json"
                    name = self.add_workspace_file(directory, "generated" + suffix, tracked=False)
                    (self.directory / name).write_text("unformatted generated evidence  \n{invalid JSON  ")
                for mode in ("format", "lint", "comments", "harness", "git-tracked"):
                    result = self.check(mode)
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_wrong_task_output_policy_is_detected(self):
        original = json.loads(json.dumps(self.registry["task_output_paths"]))
        for role, other in (("development", "agy"), ("agy", "development")):
            for kind in ("reports", "artifacts"):
                with self.subTest(role=role, kind=kind):
                    paths = json.loads(json.dumps(original))
                    paths[role][kind] = paths[other][kind]
                    self.update_registry(task_output_paths=paths)
                    result = self.check("harness")
                    self.assertEqual(result.returncode, 1)
                    self.assertIn("task output path policy drift", result.stderr)
        self.update_registry(task_output_paths=original)

    def test_wrong_agent_output_instructions_are_detected(self):
        instructions = (
            ("codex", "harness/agents/codex-developer.md", "development", "codex"),
            ("claude", "CLAUDE.md", "development", "claude"),
            ("agy", "harness/agents/agy-reviewer.md", "agy", "development"),
        )
        for producer, instruction, expected, other in instructions:
            path = self.directory / instruction
            original = path.read_text()
            path.write_text(original.replace(f"reports/{expected}/", f"reports/{other}/"))
            result = self.check("harness")
            self.assertEqual(result.returncode, 1)
            self.assertIn("output instructions drift", result.stderr)
            path.write_text(original)

    def test_same_task_handoff_updates_shared_evidence_without_registry_change(self):
        registry_before = (self.directory / "harness/registry.json").read_bytes()
        report = self.directory / self.registry["report"]
        report.parent.mkdir(parents=True, exist_ok=True)
        for contributor, next_contributor in (("codex", "claude"), ("claude", "codex")):
            with self.subTest(contributor=contributor, next_contributor=next_contributor):
                report.write_text(
                    f"contributors:\n- codex\n- claude\nfinalized_by: {contributor}\n", encoding="utf-8",
                )
                checkpoint = self.directory / "harness/workspace/checkpoints/synthetic-handoff.md"
                checkpoint.write_text(
                    f"current_contributor: {contributor}\nnext_contributor: {next_contributor}\n", encoding="utf-8",
                )
                result = self.check("harness")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual((self.directory / "harness/registry.json").read_bytes(), registry_before)

    def test_current_task_report_cannot_use_agent_or_reviewer_path(self):
        previous = self.registry["report"]
        task = self.directory / "harness/workspace/current-task.md"
        original = task.read_text()
        for identity in ("codex", "claude", "agy"):
            with self.subTest(identity=identity):
                wrong = f"harness/workspace/reports/{identity}/synthetic-task.md"
                task.write_text(original.replace(
                    previous.removeprefix("harness/workspace/"), wrong.removeprefix("harness/workspace/"),
                ))
                self.update_registry(report=wrong)
                result = self.check("harness")
                self.assertEqual(result.returncode, 1)
                self.assertIn("current-task report must use shared development path", result.stderr)

    def test_active_producer_control_is_rejected(self):
        self.update_registry(active_producer="codex")
        result = self.check("harness")
        self.assertEqual(result.returncode, 1)
        self.assertIn("active producer must not gate same-task handoff", result.stderr)

    def test_generated_outputs_can_be_absent_while_registered_inputs_remain(self):
        # BOUNDARY: 디렉터리 삭제 fixture도 명시적인 strict 입력은 보존한다. 생성물 부재만 검증한다.
        anchors = [self.directory / name for names in self.registry["workspace_static_files"].values() for name in names]
        saved = {path: path.read_bytes() for path in anchors if path.is_file()}
        for directory in (
            "reports/development", "reports/agy",
            "artifacts/development", "artifacts/agy",
        ):
            shutil.rmtree(self.directory / "harness/workspace" / directory, ignore_errors=True)
        for path, data in saved.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        for mode in ("format", "harness", "git-tracked"):
            result = self.check(mode)
            self.assertEqual(result.returncode, 0, result.stderr)

    def update_registry(self, **changes):
        self.registry.update(changes)
        (self.directory / "harness/registry.json").write_text(
            json.dumps(self.registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
        )

    def test_historical_initial_review_is_complete_but_current_task_is_pending(self):
        self.update_registry(agy_review="review_complete",
            agy_review_evidence="harness/workspace/reports/agy/agy-initial-harness-review.md")
        result = self.check("harness")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("recorded_result=pass_with_fixes", result.stdout)
        self.assertIn("CURRENT REPORT REVIEW: pending; human review PENDING", result.stdout)

    def test_targeted_review_is_complete_but_current_task_is_pending(self):
        self.update_registry(agy_review="review_complete",
            agy_review_evidence="harness/workspace/reports/agy/agy-harness-fix-review.md")
        result = self.check("harness")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("recorded_result=pass; reviewed_report=harness/workspace/reports/codex/2026-09-27-codex-harness-fix-report.md", result.stdout)
        self.assertIn("CURRENT REPORT REVIEW: pending; human review PENDING", result.stdout)
        self.assertNotIn("harness/workspace/reports/agy/agy-harness-fix-review.md", self.registry["required_files"])

    def add_workspace_file(self, directory, filename, tracked=True):
        name = f"harness/workspace/{directory}/{filename}"
        path = self.directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# 합성 기록\n\n회귀 테스트용 기록이며 실제 Review 판정이 아니다.\n", encoding="utf-8")
        if tracked:
            self.git("add", "-f", "--", name)
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

    def test_generated_outputs_do_not_hide_executable_source(self):
        for directory in ("reports", "checkpoints"):
            for filename in ("malicious.py", "script.sh"):
                with self.subTest(directory=directory, filename=filename):
                    name = self.add_workspace_file(directory, filename)
                    result = self.check("harness")
                    self.assertEqual(result.returncode, 1)
                    self.assertIn("Registry drift", result.stderr)
                    self.remove_workspace_file(name)

    def test_generated_symlink_is_not_followed_or_gating(self):
        name = "harness/workspace/reports/symlink.md"
        (self.directory / name).symlink_to(self.directory / "missing-outside-input")
        self.git("add", "-f", "--", name)
        for mode in ("format", "lint", "comments", "harness", "git-tracked"):
            result = self.check(mode)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_untracked_reports_and_checkpoints_with_whitespace_are_non_gating(self):
        ignore = self.directory / ".gitignore"
        ignore.write_text(ignore.read_text().replace("/harness/workspace/reports/**/*.md\n", "")
            .replace("/harness/workspace/checkpoints/**/*.md\n", ""))
        self.git("add", "--", ".gitignore")
        for directory in ("reports", "checkpoints"):
            name = self.add_workspace_file(directory, "untracked.md", tracked=False)
            (self.directory / name).write_text("# 합성 생성물  \n[존재하지 않는 출력 링크](missing.md)\n")
        for mode in ("format", "lint", "comments", "harness", "git-tracked"):
            result = self.check(mode)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_ignored_reports_and_checkpoints_are_non_gating(self):
        for directory in ("reports", "checkpoints"):
            name = self.add_workspace_file(directory, "ignored.md", tracked=False)
            (self.directory / name).write_text("invalid report whitespace  ")
        for mode in ("format", "harness", "git-tracked"):
            result = self.check(mode)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_tracked_generated_whitespace_and_unstaged_changes_are_non_gating(self):
        for directory in ("reports", "checkpoints"):
            name = self.add_workspace_file(directory, "tracked.md")
            path = self.directory / name
            path.write_text("staged output  \n")
            self.git("add", "-f", "--", name)
            path.write_text("unstaged output  ")
        for mode in ("format", "harness", "git-tracked"):
            result = self.check(mode)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_untracked_malformed_artifacts_are_non_gating(self):
        ignore = self.directory / ".gitignore"
        ignore.write_text(ignore.read_text().replace("/harness/workspace/artifacts/**/*.json\n", "")
            .replace("/harness/workspace/artifacts/**/*.log\n", ""))
        self.git("add", "--", ".gitignore")
        for filename in ("result.json", "run.log"):
            (self.directory / "harness/workspace/artifacts" / filename).write_text("{broken JSON  ")
        for mode in ("format", "lint", "comments", "harness", "git-tracked"):
            result = self.check(mode)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_ignored_malformed_artifacts_are_non_gating(self):
        (self.directory / "harness/workspace/artifacts/result.json").write_text("{broken JSON  ")
        for mode in ("format", "lint", "harness", "git-tracked"):
            result = self.check(mode)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_control_task_and_static_readmes_remain_format_gated(self):
        for name in ("harness/workspace/current-task.md", "harness/workspace/checkpoints/README.md", "harness/workspace/artifacts/README.md"):
            with self.subTest(name=name):
                path = self.directory / name
                original = path.read_text()
                path.write_text(original + "invalid static whitespace  \n")
                result = self.check("format")
                self.assertEqual(result.returncode, 1)
                self.assertIn("trailing whitespace", result.stderr)
                path.write_text(original)

    def test_product_and_harness_rule_whitespace_remain_gated(self):
        for name in ("scripts/phase0.py", "harness/rules/git-policy.md"):
            path = self.directory / name
            original = path.read_text()
            path.write_text(original + "# 합성 공백 오류  \n")
            result = self.check("format")
            self.assertEqual(result.returncode, 1)
            self.assertIn("trailing whitespace", result.stderr)
            path.write_text(original)

    def test_product_untracked_file_is_still_rejected(self):
        path = self.directory / "data-pipeline/src/biz_aid_pipeline/untracked.py"
        path.write_text("value = 1\n")
        result = self.check("git-tracked")
        self.assertEqual(result.returncode, 1)
        self.assertIn("untracked project files", result.stderr)

    def test_workspace_control_and_readme_cannot_be_ignored(self):
        path = self.directory / ".gitignore"
        original = path.read_text()
        for name in ("harness/workspace/current-task.md", "harness/workspace/artifacts/README.md", "harness/workspace/checkpoints/README.md"):
            path.write_text(original + f"/{name}\n")
            self.git("add", "--", ".gitignore")
            result = self.check("git-tracked")
            self.assertEqual(result.returncode, 1)
            self.assertIn("required files are ignored", result.stderr)
        path.write_text(original)

    def test_static_readme_links_remain_strict(self):
        path = self.directory / "harness/workspace/artifacts/README.md"
        path.write_text(path.read_text() + "\n[누락된 입력](../../../missing-input.md)\n")
        result = self.check("harness")
        self.assertEqual(result.returncode, 1)
        self.assertIn("broken/outside", result.stderr)

    def test_no_generated_outputs_is_valid(self):
        static = {name for names in self.registry["workspace_static_files"].values() for name in names}
        for directory in ("reports", "checkpoints", "artifacts"):
            for path in (self.directory / "harness/workspace" / directory).rglob("*"):
                if path.is_file() and str(path.relative_to(self.directory)) not in static:
                    path.unlink()
        for mode in ("format", "lint", "comments", "harness", "git-tracked"):
            result = self.check(mode)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PENDING: independent AGY review", result.stdout if mode == "harness" else self.check("harness").stdout)

    def test_report_creation_after_validation_does_not_invalidate_result(self):
        first = self.check("harness")
        self.assertEqual(first.returncode, 0, first.stderr)
        name = self.add_workspace_file("reports", "after-validation.md", tracked=False)
        (self.directory / name).write_text("post-validation report  ")
        for mode in ("format", "git-tracked", "harness"):
            result = self.check(mode)
            self.assertEqual(result.returncode, 0, result.stderr)

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
        self.update_registry(agy_review="review_complete", agy_review_evidence=name)
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

    def test_nested_generated_outputs_and_executable_markdown_are_not_executed(self):
        for directory in ("reports", "checkpoints"):
            for filename in ("nested/report.md", "executable.md"):
                name = self.add_workspace_file(directory, filename)
                path = self.directory / name
                path.write_text("generated whitespace  ")
                path.chmod(0o755)
        for mode in ("format", "lint", "comments", "harness", "git-tracked"):
            result = self.check(mode)
            self.assertEqual(result.returncode, 0, result.stderr)

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
        self.update_registry(agy_review="pending",
            agy_review_evidence="harness/workspace/reports/agy/agy-harness-fix-review.md")
        result = self.check("harness")
        self.assertEqual(result.returncode, 1)
        self.assertIn("pending requires null evidence", result.stderr)

    def test_unknown_review_state_is_rejected(self):
        self.update_registry(agy_review="approved_by_codex")
        result = self.check("harness")
        self.assertEqual(result.returncode, 1)
        self.assertIn("unsupported lifecycle state", result.stderr)

    def test_complete_without_evidence_is_rejected(self):
        self.update_registry(agy_review="review_complete", agy_review_evidence=None)
        result = self.check("harness")
        self.assertEqual(result.returncode, 1)
        self.assertIn("independent evidence must be user-acknowledged", result.stderr)

    def test_development_producer_report_cannot_be_independent_review_evidence(self):
        claude_report = self.add_workspace_file("reports/claude", "synthetic-task.md")
        codex_report = self.add_workspace_file("reports/codex", "synthetic-task.md")
        for report in (self.registry["report"], codex_report, claude_report):
            with self.subTest(report=report):
                self.update_registry(agy_review="review_complete", agy_review_evidence=report)
                result = self.check("harness")
                self.assertEqual(result.returncode, 1)
                self.assertIn("independent evidence must be user-acknowledged", result.stderr)

    def test_missing_independent_review_is_unverified_but_build_passes(self):
        evidence = "harness/workspace/reports/agy/agy-harness-fix-review.md"
        self.update_registry(agy_review="review_complete", agy_review_evidence=evidence)
        (self.directory / evidence).unlink()
        result = self.check("harness")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("EVIDENCE INTEGRITY: UNAVAILABLE", result.stdout)

    def test_forged_complete_heading_does_not_verify_independent_review(self):
        evidence = "harness/workspace/reports/agy/agy-harness-fix-review.md"
        self.update_registry(agy_review="review_complete", agy_review_evidence=evidence)
        path = self.directory / evidence
        path.write_text("# AGY Initial Harness Review\n\n**Reviewer**: AGY\n\n## PASS\n\nReview Status: COMPLETE\n", encoding="utf-8")
        result = self.check("harness")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("EVIDENCE INTEGRITY: MISMATCH", result.stdout)
        self.assertIn("CURRENT REPORT REVIEW: pending", result.stdout)

    def test_review_basis_report_change_invalidates_the_evidence(self):
        self.update_registry(agy_review="review_complete",
            agy_review_evidence="harness/workspace/reports/agy/agy-harness-fix-review.md")
        path = self.directory / "harness/workspace/reports/codex/2026-09-27-codex-harness-fix-report.md"
        path.write_text(path.read_text(encoding="utf-8") + "\n변경된 검토 대상\n", encoding="utf-8")
        result = self.check("harness")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("EVIDENCE INTEGRITY: MISMATCH", result.stdout)

    def test_external_symlink_cannot_replace_independent_review(self):
        evidence = "harness/workspace/reports/agy/agy-harness-fix-review.md"
        self.update_registry(agy_review="review_complete", agy_review_evidence=evidence)
        path = self.directory / evidence
        path.unlink()
        path.symlink_to(ROOT / evidence)
        result = self.check("harness")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("EVIDENCE INTEGRITY: UNSAFE", result.stdout)

    def test_stale_registry_report_cannot_approve_the_current_task(self):
        self.update_registry(report="harness/workspace/reports/codex/2026-09-27-codex-harness-report.md")
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

    def test_only_intellij_introspection_meta_cache_is_allowed(self):
        cache = self.directory / ".idea/dataSources/84cac05d/storage_v2/_src_/schema"
        cache.mkdir(parents=True)
        allowed = cache / "information_schema.FNRwLQ.meta"
        allowed.write_text("#n:information_schema\n", encoding="utf-8")
        result = self.check("git-tracked")
        self.assertEqual(result.returncode, 0, result.stderr)
        rejected = [cache / f"information_schema{suffix}" for suffix in (".txt", ".db", ".json", ".md", ".py", ".sh")]
        rejected += [self.directory / ".idea/dataSources/84cac05d/other.meta", self.directory / ".idea/cache.meta",
                     self.directory / ".idea/dataSources/storage_v2.meta"]
        for path in rejected:
            with self.subTest(path=str(path.relative_to(self.directory))):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("hidden\n", encoding="utf-8")
                result = self.check("git-tracked")
                self.assertEqual(result.returncode, 1)
                self.assertIn("ignored project result", result.stderr)
                path.unlink()
        # 실행 권한이 있으면 같은 이름 규칙이라도 IDE cache로 보지 않는다.
        allowed.chmod(0o755)
        result = self.check("git-tracked")
        self.assertEqual(result.returncode, 1)
        self.assertIn("ignored project result", result.stderr)

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
        ignored = subprocess.run(["git", "check-ignore", "--no-index", ".env.dev.example"],
                                 cwd=self.directory, capture_output=True, text=True)
        self.assertEqual(ignored.returncode, 1)
        tracked = subprocess.check_output(["git", "ls-files", ".env.dev.example"], cwd=self.directory, text=True)
        self.assertEqual(tracked.strip(), ".env.dev.example")

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
        path.write_text(path.read_text(encoding="utf-8") + "\n.env.dev.example\n", encoding="utf-8")
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

    def test_forbidden_top_level_module_cannot_be_silently_added(self):
        (self.directory / "ai").mkdir()
        result = self.check("harness")
        self.assertEqual(result.returncode, 1)
        self.assertIn("forbidden top-level product module added", result.stderr)

    def test_ci_branch_drift_is_detected(self):
        path = self.directory / ".github/workflows/ci.yml"
        path.write_text(path.read_text(encoding="utf-8").replace("branches: [dev]", "branches: [prod]"), encoding="utf-8")
        result = self.check("harness")
        self.assertEqual(result.returncode, 1)
        self.assertIn("CI must enforce dev", result.stderr)

    def test_english_explanatory_comment_is_rejected(self):
        path = self.directory / "scripts/phase0.py"
        path.write_text(path.read_text(encoding="utf-8") + "\n# explanatory English comment\n", encoding="utf-8")
        result = self.check("comments")
        self.assertEqual(result.returncode, 1)
        self.assertIn("requires Korean", result.stderr)

    def test_english_comment_in_service_code_is_rejected_but_strings_are_not_comments(self):
        path = self.directory / "frontend/src/shared/api/client.ts"
        source = path.read_text(encoding="utf-8")
        # 문자열 안의 // 는 주석이 아니므로 통과해야 한다.
        path.write_text(source + '\nexport const sample = "http://localhost/*not-comment*/";\n', encoding="utf-8")
        self.assertEqual(self.check("comments").returncode, 0)
        path.write_text(source + "\n// explanatory English comment\n", encoding="utf-8")
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
