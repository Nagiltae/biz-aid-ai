import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data-pipeline/src"))

from biz_aid_pipeline.parsing.corpus import Progress, drive, select_sources


class CorpusParsingContractTests(unittest.TestCase):
    def run_drive(self, sources, existing, outcomes, skip=("PARSED",), **options):
        executed, written = [], []

        def execute(sha):
            executed.append(sha)
            return dict(outcomes.get(sha, {"status": "PARSED", "failure_code": None}))
        progress = Progress("t", len(sources))
        drive(sources, lambda sha, fmt: "key-" + sha, lambda sha, key: existing.get(sha), execute, progress, set(skip),
              lambda sha, fmt, outcome, current: written.append((sha, outcome["status"])), **options)
        return progress, executed, written

    def test_only_enabled_formats_are_selected_once_in_sha_order(self):
        rows = [("c" * 64, "PDF"), ("a" * 64, "HWPX"), ("c" * 64, "PDF"), ("b" * 64, "ZIP"), ("0" * 64, "HWP")]
        # unique content SHA 하나가 실행 단위이고 비활성 format(ZIP)은 대상이 아니다.
        self.assertEqual(select_sources(rows, ["PDF", "HWP", "HWPX"]),
                         [("0" * 64, "HWP"), ("a" * 64, "HWPX"), ("c" * 64, "PDF")])

    def test_current_parse_key_results_are_skipped_on_resume(self):
        sources = [("a" * 64, "PDF"), ("b" * 64, "PDF")]
        progress, executed, written = self.run_drive(sources, {"a" * 64: "PARSED"}, {})
        # BOUNDARY: 현재 key로 이미 완료된 source는 다시 parsing하지 않는다.
        self.assertEqual(executed, ["b" * 64])
        self.assertEqual((progress.skipped, progress.completed, progress.state), (1, 2, "COMPLETED"))
        self.assertEqual(written[0], ("a" * 64, "PARSED"))

    def test_source_failure_is_isolated_and_environment_failures_stop_the_run(self):
        sources = [(sha * 64, "PDF") for sha in "abcdef"]
        progress, executed, _ = self.run_drive(sources, {}, {"a" * 64: {"status": "EXECUTION_FAILED", "failure_code": "source_timeout"}})
        # source 하나의 timeout은 기록만 하고 다음 source로 넘어간다.
        self.assertEqual(len(executed), 6)
        self.assertEqual((progress.statuses["EXECUTION_FAILED"], progress.failures["source_timeout"], progress.state),
                         (1, 1, "COMPLETED"))
        storage = {"status": "EXECUTION_FAILED", "failure_code": "document_source_s3_read_failure"}
        progress, executed, _ = self.run_drive(sources, {}, {sha * 64: storage for sha in "bcd"})
        # 저장소·인증 실패가 연속되면 남은 source를 실패로 기록하지 않고 환경 문제로 멈춘다.
        self.assertEqual((executed, progress.state, progress.stop_reason),
                         (["a" * 64, "b" * 64, "c" * 64, "d" * 64], "STOPPED_ENVIRONMENT", "document_source_s3_read_failure"))

    def test_upper_bound_and_stop_request_end_at_a_source_boundary(self):
        sources = [(sha * 64, "PDF") for sha in "abcdef"]
        # 완료(skip 포함)가 상한에 닿으면 다음 source를 시작하지 않는다. 앞의 skip도 완료로 센다.
        progress, executed, _ = self.run_drive(sources, {"a" * 64: "PARSED"}, {}, max_completed=3)
        self.assertEqual((executed, progress.completed, progress.state), (["b" * 64, "c" * 64], 3, "STOPPED_LIMIT"))
        # 종료 요청은 실행 중 source를 끊지 않고 다음 source 경계에서만 반영된다.
        requests = iter([False, False, True])
        progress, executed, _ = self.run_drive(sources, {}, {}, stop_requested=lambda: next(requests))
        self.assertEqual((executed, progress.state), (["a" * 64, "b" * 64], "STOPPED_SIGNAL"))


if __name__ == "__main__":
    unittest.main()
