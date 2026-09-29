import json
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from evals.table_engine.common import (adjacency, compare_to_gt, critical_tokens, html_cells, make_table,
                                       match_tables)
from evals.table_engine.evaluate import consensus_regions
from evals.table_engine.pp_analysis import (detection_rows, grid_cells, html_row_counts, normalize_overlaps,
                                            reading_order_text, structure_boxes)
from evals.table_engine import visuals
from evals.table_engine.visuals import (VL_CALL_TIMEOUT_SECONDS, chart_table, degenerate, review_bundle,
                                        visual_quality)
from evals.table_engine.run_engine import camelot_cells
from evals.table_engine.assemble import (contained, loss_pages, outside_cell_words, region_items, rescue_children,
                                        resolve_overlaps, spill_words)
from evals.table_engine.review import DECISIONS, visual_flags


def grid(rows, merged=()):
    cells = [{"row": r, "col": c, "text": text} for r, row in enumerate(rows) for c, text in enumerate(row) if text is not None]
    for row, col, rowspan, colspan in merged:
        for cell in cells:
            if (cell["row"], cell["col"]) == (row, col):
                cell.update(rowspan=rowspan, colspan=colspan)
    return make_table(1, (0, 0, 100, 100), cells)


class TableEngineEvaluationContractTests(unittest.TestCase):
    def test_critical_tokens_classify_once_with_priority(self):
        tokens = critical_tokens("지원금 5천만원(정부 80 %) 2026. 9. 15.까지 12개월, 총 1,234건")
        self.assertEqual(tokens, Counter({("amount", "5천만원"): 1, ("percent", "80%"): 1, ("date", "2026.9.15"): 1,
                                          ("period", "12개월"): 1, ("number", "1,234"): 1}))

    def test_html_cells_respect_rowspan_and_colspan(self):
        cells = html_cells("<table><tr><td rowspan='2'>구분</td><td colspan='2'>지원</td></tr>"
                           "<tr><td>정부</td><td>기업</td></tr></table>")
        self.assertEqual([(c["row"], c["col"], c["rowspan"], c["colspan"], c["text"]) for c in cells],
                         [(0, 0, 2, 1, "구분"), (0, 1, 1, 2, "지원"), (1, 1, 1, 1, "정부"), (1, 2, 1, 1, "기업")])

    def test_match_tables_is_one_to_one_by_page_and_iou(self):
        reference = [make_table(1, (0, 0, 100, 100), []), make_table(2, (0, 0, 100, 100), [])]
        candidate = [make_table(1, (0, 0, 90, 100), []), make_table(1, (0, 0, 100, 100), []),
                     make_table(2, (200, 200, 300, 300), [])]
        self.assertEqual({k: v[0] for k, v in match_tables(reference, candidate).items()}, {0: 1})

    def test_compare_to_gt_scores_perfect_missing_and_dropped_tables(self):
        gt = grid([["구분", "정부", "기업"], ["컨설팅", "80%", "20%"], ["한도", "5천만원", None]], merged=[(2, 1, 1, 2)])
        perfect = compare_to_gt(gt, gt)
        self.assertEqual((perfect["cell_recall"], perfect["cell_text_recall"], perfect["critical_token_recall"],
                          perfect["merged_cell_accuracy"], perfect["adjacency_f1"], perfect["structure_exact"]),
                         (1.0, 1.0, 1.0, 1.0, 1.0, True))
        absent = compare_to_gt(gt, None)
        self.assertEqual((absent["detected"], absent["critical_token_recall"], absent["critical_tokens_missing_count"]),
                         (False, 0.0, 3))
        dropped = compare_to_gt(gt, grid([["구분", "정부", "기업"], ["컨설팅", "80%", ""], ["한도", "5천만원", None]]))
        self.assertLess(dropped["cell_recall"], 1.0)
        self.assertEqual(dropped["critical_tokens_missing"], ["percent:20%"])
        self.assertEqual(dropped["merged_cell_accuracy"], 0.0)

    def test_adjacency_skips_cells_covered_by_a_span(self):
        table = grid([["A", "B", "C"], ["D", None, "E"]], merged=[(0, 1, 2, 1)])
        relations = adjacency(table)
        self.assertEqual(relations[("A", "B", "h")], 1)
        self.assertEqual(relations[("D", "B", "h")], 1)
        self.assertEqual(relations[("B", "E", "h")], 1)

    def test_consensus_requires_two_engine_families(self):
        table = {"page": 1, "bbox": [0, 0, 100, 100], "cells": []}
        camelot_only = {f"camelot-{f}": {"s": {"engine": "camelot", "tables": [table]}} for f in ("lattice", "stream")}
        self.assertEqual(consensus_regions(camelot_only, "s"), [])
        mixed = dict(camelot_only, **{"docling_tableformer-default": {"s": {"engine": "docling_tableformer", "tables": [table]}}})
        self.assertEqual(len(consensus_regions(mixed, "s")), 1)

    def test_camelot_lattice_spans_come_from_missing_internal_edges(self):
        def cell(text, right=True, bottom=True):
            return SimpleNamespace(text=text, right=right, bottom=bottom)
        lattice = SimpleNamespace(flavor="lattice", cells=[[cell("합계", right=False), cell(""), cell("100")],
                                                           [cell("A"), cell("B"), cell("C")]])
        spans = sorted((c["row"], c["col"], c["rowspan"], c["colspan"], c["text"]) for c in camelot_cells(lattice))
        self.assertEqual(spans, [(0, 0, 1, 2, "합계"), (0, 2, 1, 1, "100"), (1, 0, 1, 1, "A"), (1, 1, 1, 1, "B"),
                                 (1, 2, 1, 1, "C")])
        stream = SimpleNamespace(flavor="stream", cells=lattice.cells)
        self.assertTrue(all(c["rowspan"] == c["colspan"] == 1 for c in camelot_cells(stream)))

    def test_pp_row_rule_and_html_row_counts(self):
        rows = detection_rows([[100, 0, 200, 20], [0, 5, 100, 20], [0, 40, 200, 60]])
        self.assertEqual([[b[0] for b in row] for row in rows], [[0, 100], [0]])
        tokens = ["<table>", "<tr>", "<td", ' colspan="2"', ">", "</td>", "</tr>", "<tr>", "<td></td>", "<td></td>", "</tr>"]
        self.assertEqual(html_row_counts(tokens), [1, 2])

    def test_grid_from_detection_edges_proves_spans_or_reports_conflicts(self):
        cells, stats = grid_cells([[0, 0, 200, 20], [0, 20, 100, 40], [100, 20, 200, 40]])
        self.assertEqual(sorted((c["row"], c["col"], c["rowspan"], c["colspan"]) for c in cells),
                         [(0, 0, 1, 2), (1, 0, 1, 1), (1, 1, 1, 1)])
        self.assertEqual((stats["grid_conflicts"], stats["uncovered_slots"]), (0, 0))
        _, overlapped = grid_cells([[0, 0, 100, 20], [0, 0, 100, 20]])
        self.assertEqual(overlapped["grid_conflicts"], 1)

    def test_structure_bbox_is_rescaled_from_long_side_normalization(self):
        record = {"table_box_px": [100, 200, 1100, 450], "structure_bbox_crop": [[0, 0, 1000, 1000]]}
        self.assertEqual(structure_boxes(record), [[100.0, 200.0, 1100.0, 450.0]])

    def test_overlap_normalization_keeps_one_side_of_containment(self):
        outer, inner, other = [0, 0, 100, 40], [0, 0, 50, 20], [100, 0, 200, 40]
        self.assertEqual(normalize_overlaps([outer, inner, other], "larger"), [outer, other])
        self.assertEqual(normalize_overlaps([outer, inner, other], "smaller"), [inner, other])

    def test_failed_table_text_is_reassembled_in_reading_order(self):
        parts = [([60, 30, 90, 40], "둘째줄"), ([10, 0, 40, 10], "첫"), ([45, 1, 70, 11], "줄")]
        self.assertEqual(reading_order_text(parts), "첫 줄\n둘째줄")

    def test_overlapping_pp_regions_are_preserved_as_failed_union_without_choosing(self):
        def row(page, box, verdict):
            return {"sha256": "a" * 64, "page": page, "bbox_pt": box,
                    "quality": {"grid": {"verdict": verdict, "reasons": []}}}
        rows = [row(1, [0, 0, 100, 100], "TABLE_VALID"), row(1, [10, 10, 60, 60], "TABLE_VALID"),
                row(1, [0, 200, 50, 250], "TABLE_VALID"), row(2, [10, 10, 60, 60], "TABLE_VALID")]
        resolved = resolve_overlaps(rows)
        self.assertEqual(len(resolved), 3)
        union = next(r for r in resolved if "members" in r)
        # 겹친 두 영역은 어느 쪽도 표로 채택하지 않고 합친 영역의 native text 보존 대상으로 남는다.
        self.assertEqual((union["bbox_pt"], union["quality"]["grid"]["verdict"], len(union["members"])),
                         ([0, 0, 100, 100], "TABLE_QUALITY_FAILED", 2))
        self.assertEqual(union["quality"]["grid"]["reasons"], ["unresolved_overlapping_pp_regions"])
        self.assertEqual(sum(r["quality"]["grid"]["verdict"] == "TABLE_VALID" for r in resolved), 2)

    def test_loss_is_measured_per_page_against_baseline(self):
        native = {1: Counter("가나다"), 2: Counter("라마")}
        baseline = {1: Counter("가나다"), 2: Counter("라")}
        # 1쪽에서 잃은 글자는 2쪽에서 새로 찾은 글자로 상쇄되지 않는다.
        assembled = {1: Counter("가나"), 2: Counter("라마")}
        self.assertEqual(loss_pages(native, baseline, assembled, Counter({1: 1})),
                         [{"page": 1, "lost_vs_baseline": 1, "lost_chars": "다", "pp_regions_on_page": 1}])
        self.assertEqual(loss_pages(native, baseline, baseline, Counter()), [])

    def test_deleting_a_table_keeps_its_caption_and_footnote_children(self):
        from docling_core.types.doc import DocItemLabel, DoclingDocument, TableData
        document = DoclingDocument(name="t")
        table = document.add_table(data=TableData(num_rows=1, num_cols=1, table_cells=[]))
        document.add_text(label=DocItemLabel.FOOTNOTE, text="※ 표 아래 주석", parent=table)
        replacement = document.add_text(label=DocItemLabel.TEXT, text="대체 text")
        stats = Counter()
        rescue_children(document, [table], [table], replacement, stats)
        document.delete_items(node_items=[table])
        # 부모 표를 지워도 영역 밖 footnote는 같은 label로 남아야 한다(3-B.4 corpus 조립에서 관찰된 손실).
        self.assertEqual([(t.label, t.text) for t in document.texts if t.text.startswith("※")],
                         [(DocItemLabel.FOOTNOTE, "※ 표 아래 주석")])
        self.assertEqual(stats["children_rescued"], 1)

    def test_valid_table_words_outside_cells_and_partial_items_are_not_dropped(self):
        words = [([0, 0, 5, 5], "‣"), ([10, 0, 20, 5], "구분"), ([30, 0, 40, 5], "금액")]
        cells = [{"text": "구분"}, {"text": "금액"}]
        self.assertEqual(outside_cell_words(words, cells), [([0, 0, 5, 5], "‣")])
        self.assertTrue(contained([0, 0, 100, 100], [1, -1, 101, 50]))
        self.assertFalse(contained([0, 0, 100, 100], [-20, 10, 60, 20]))

    def test_region_ownership_includes_picture_text_and_keeps_partial_items(self):
        from docling_core.types.doc import BoundingBox, CoordOrigin, DocItemLabel, DoclingDocument, ProvenanceItem, Size
        document = DoclingDocument(name="t")
        document.add_page(page_no=1, size=Size(width=600, height=800))

        def prov(l, t, r, b):
            return ProvenanceItem(page_no=1, bbox=BoundingBox(l=l, t=t, r=r, b=b, coord_origin=CoordOrigin.TOPLEFT), charspan=(0, 1))
        picture = document.add_picture(prov=prov(100, 100, 300, 200))
        inside = document.add_text(label=DocItemLabel.TEXT, text="그림 안 글자", prov=prov(120, 120, 200, 140), parent=picture)
        partial = document.add_text(label=DocItemLabel.SECTION_HEADER, text="걸친 제목", prov=prov(20, 150, 200, 170))
        owned, kept = region_items(document, 1, [100, 100, 300, 200])
        # picture 자식 text는 PP 영역이 소유하고, 영역 밖으로 걸친 제목은 지우지 않는다.
        self.assertTrue(any(item is inside for item in owned))
        self.assertTrue(any(item is partial for item in kept) and not any(item is partial for item in owned))

    def test_spill_words_keep_text_outside_every_region_without_duplication(self):
        words = [([10, 10, 20, 20], "(단위:"), ([110, 110, 120, 120], "표안"), ([10, 300, 20, 310], "주석")]
        spill = spill_words(words, [0, 0, 400, 400], [[100, 100, 200, 200]], [[0, 290, 50, 320]])
        self.assertEqual(spill, [([10, 10, 20, 20], "(단위:")])

    def test_review_flags_point_to_evidence_without_deciding(self):
        flags = visual_flags("신청 → 접수 2026", {"task": "OCR:", "output": "접수 ← 신청 首色 2027", "error": None})
        joined = " ".join(flags["flags"])
        for expected in ("원문에 없는 한자", "화살표", "원문 수치 1개 누락", "원문에 없는 수치 1개"):
            self.assertIn(expected, joined)
        self.assertIn("timeout", visual_flags("", {"task": "OCR:", "output": "", "error": "TimeoutError: vl_call_timeout:120s"})["flags"])
        # 사람 선택지에는 자동 PASS 값이 없고 불확실을 고를 수 있다.
        self.assertEqual([v for v, _ in DECISIONS["visual"]], ["usable", "unusable", "uncertain"])
        self.assertIn("uncertain", [v for v, _ in DECISIONS["container"]])

    def test_visual_quality_separates_execution_from_content(self):
        self.assertEqual(VL_CALL_TIMEOUT_SECONDS, 120)
        picture = {"native_text": "지원금 신청 절차 2026. 9. 15. 80%"}
        base = {"task": "OCR:", "error": None}
        self.assertEqual(visual_quality(dict(base, output=""), picture)["reasons"], ["empty_output"])
        self.assertIn("degenerate_repetition", visual_quality(dict(base, output="반복되는문장입니다 " * 12), picture)["reasons"])
        self.assertFalse(degenerate("항목<|LOC_1|><|LOC_2|><|LOC_1|><|LOC_2|> 다음<|LOC_1|><|LOC_2|>"))
        chart = visual_quality({"task": "Chart Recognition:", "error": None, "output": "제목과 축 설명"}, {})
        self.assertEqual((chart["verdict"], chart["human_review"]), ("VISUAL_VALID", "pending"))
        self.assertIsNotNone(chart_table("| 연도 | 금액 |\n| --- | --- |\n| 2025 | 10 |"))
        self.assertEqual(chart_table("  | 1 | 2\n가 | 0 | 1"), [["", "1", "2"], ["가", "0", "1"]])
        valid = visual_quality(dict(base, output="지원금 신청 절차 안내 2026. 9. 15. 80%"), picture)
        self.assertEqual((valid["verdict"], valid["native_grounding"]["recall"], valid["critical_token_recall"],
                          valid["human_review"], valid["hallucination_review"]),
                         ("VISUAL_VALID", 1.0, 1.0, "pending", "pending"))
        self.assertFalse(degenerate("서로 다른 내용이 이어지는 정상 출력입니다"))
        # 3-B.3 pilot에서 관찰된 한자 hallucination은 실행 성공과 별개로 내용 실패다. 원문에 있는 한자는 허용한다.
        self.assertEqual(visual_quality(dict(base, output="首色 | 0\n次色 | 1"), picture)["reasons"], ["unexpected_han_script"])
        self.assertEqual(visual_quality(dict(base, output="大韓 지원"), {"native_text": "大韓 지원"})["reasons"], [])
        self.assertIs(chart["chart_tabular"], False)

    def test_visual_review_bundle_preserves_pending_human_judgment(self):
        with tempfile.TemporaryDirectory() as temporary:
            previous = visuals.OUTPUT_ROOT
            visuals.OUTPUT_ROOT = Path(temporary)
            self.addCleanup(setattr, visuals, "OUTPUT_ROOT", previous)
            out = Path(temporary) / "run" / "visuals"
            (out / "crops").mkdir(parents=True)
            (out / "crops/v1.png").write_bytes(b"synthetic")
            (out / "sample.json").write_text(json.dumps([{
                "visual_id": "v1", "sha256": "a" * 64, "page": 1, "bbox": [1, 2, 3, 4], "native_text": "원문",
            }]), encoding="utf-8")
            (out / "labels.json").write_text(json.dumps([{
                "visual_id": "v1", "visual_type": "diagram", "informative": True,
            }]), encoding="utf-8")
            quality = visual_quality({"task": "OCR:", "error": None, "output": "원문"}, {"native_text": "원문"})
            (out / "vl_results.json").write_text(json.dumps({"results": [{
                "visual_id": "v1", "task": "OCR:", "seconds": 1.0, "peak_rss_mb": 10,
                "current_rss_mb": 9, "output": "<원문>", "quality": quality,
            }]}), encoding="utf-8")
            self.assertEqual(review_bundle("run"), (1, 1))
            bundle = (out / "review/index.html").read_text(encoding="utf-8")
            self.assertIn("human_verification: <b>pending</b>", bundle)
            self.assertIn("&lt;원문&gt;", bundle)

    def test_production_route_uses_pp_without_evaluation_or_vlm_code(self):
        contract = json.loads((ROOT / "contracts/schemas/document-parsing.contract.json").read_text(encoding="utf-8"))
        self.assertEqual(contract["table_engine"]["primary"], "pp_tablemagic")
        self.assertIs(contract["routes"]["PDF"]["docling_options"]["do_table_structure"], False)
        self.assertIs(contract["visual_pilot"]["production_route_change"], False)
        self.assertIn("deferred", contract["visual_pilot"]["production_status"])
        router = (ROOT / "data-pipeline/src/biz_aid_pipeline/parsing/router.py").read_text(encoding="utf-8")
        self.assertIn("parse_pdf(raw, request.source_sha256, contract, result)", router)
        # BOUNDARY: 평가 도구·VLM·후보 engine은 제품 parsing 코드로 들어오지 않는다. PP는 표 engine으로만 들어온다.
        for path in (ROOT / "data-pipeline/src/biz_aid_pipeline").rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            for forbidden in ("evals.", "camelot", "PaddleOCR-VL", "paddleocr", "vl_recognition"):
                self.assertNotIn(forbidden, source, f"{path.name} imports {forbidden}")

    def test_corpus_is_sha_pinned_with_provenance(self):
        corpus = json.loads((ROOT / "evals/table_engine/corpus.json").read_text(encoding="utf-8"))
        documents = corpus["documents"]
        groups = Counter(d["group"] for d in documents)
        self.assertEqual(groups, Counter({"docling_cell_drop": 14, "normal_table": 18}))
        self.assertEqual(len({d["sha256"] for d in documents}), len(documents))
        for document in documents:
            self.assertRegex(document["sha256"], r"^[0-9a-f]{64}$")
            self.assertTrue(document["relations"])
            self.assertTrue(document["storage_path"].endswith(document["sha256"] + ".bin"))
            if document["group"] == "docling_cell_drop":
                self.assertGreater(document["baseline_3b"]["dropped_cells"], 0)
        self.assertEqual(sum(d["baseline_3b"]["drop_events"] for d in documents), 25)
        self.assertEqual(sum(d["baseline_3b"]["dropped_cells"] for d in documents), 132)

    def test_contract_blocks_unevidenced_engine_change_and_retry_fallback(self):
        contract = json.loads((ROOT / "contracts/schemas/document-parsing.contract.json").read_text(encoding="utf-8"))
        engine = contract["table_engine"]
        self.assertEqual(engine["primary"], "pp_tablemagic")
        self.assertIn("failure-triggered retry", engine["routing_rule"])
        self.assertIn("DoclingDocument", engine["representation"])
        self.assertEqual(engine["evaluation"]["candidates"], ["docling_tableformer", "paddleocr_pp_tablemagic", "camelot"])
        self.assertIn("blocked", engine["evaluation"]["phase4_gate"])
        gate = engine["suitability_gate"]
        self.assertIs(gate["production_route_change"], True)
        self.assertIn("not the default", gate["docling_bbox_gate"])
        self.assertIn("does not revert", gate["no_automatic_regression"])
        quality = engine["table_quality"]
        self.assertEqual(quality["evidence_states"], ["TABLE_VALID", "TABLE_QUALITY_FAILED"])
        self.assertIs(quality["parse_status_change"], False)
        self.assertIn("never a silent fallback", quality["mapping_rule"])
        self.assertIn("must not enter Chunking", quality["downstream_rule"])


if __name__ == "__main__":
    unittest.main()
