import copy
import dataclasses
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data-pipeline/src"))

from docling_core.types.doc import (BoundingBox, CoordOrigin, DocItemLabel, DoclingDocument, ProvenanceItem, Size,
                                    TableCell, TableData)
from docling_core.types.doc.common.meta import BaseMeta

from biz_aid_pipeline.chunking.chunker import (ChunkSource, chunk_document, chunk_set_key, chunker_identity,
                                               chunking_contract)
from biz_aid_pipeline.chunking.source import current_parse_key
from biz_aid_pipeline.config.settings import PipelineError
from biz_aid_pipeline.parsing.hwp_pdf import HwpConversionError
from biz_aid_pipeline.parsing.models import artifact_files, parse_key, parsing_contract, scoped_artifacts_sha256


def meta(name, value):
    item_meta = BaseMeta()
    item_meta.set_custom_field("bizaid", name, value)
    return item_meta


def prov(page, top):
    return ProvenanceItem(page_no=page, charspan=(0, 1),
                          bbox=BoundingBox(l=50, t=top, r=500, b=top + 20, coord_origin=CoordOrigin.TOPLEFT))


def sample_document():
    document = DoclingDocument(name="sample")
    document.add_page(page_no=1, size=Size(width=600, height=800))
    document.add_page(page_no=2, size=Size(width=600, height=800))
    document.add_heading("빈 절", level=1, prov=prov(1, 20))
    document.add_heading("지원대상", level=1, prov=prov(1, 50))
    document.add_heading("업력 조건", level=2, prov=prov(1, 80))
    text = document.add_text(label=DocItemLabel.TEXT, text="공고일 기준 업력 3년 이하 기업", prov=prov(1, 110))
    text.meta = meta("hwpx", {"section": "Contents/section0.xml", "path": "p[3]"})
    cells = [TableCell(text=value, start_row_offset_idx=row, end_row_offset_idx=row + 1, start_col_offset_idx=col,
                       end_col_offset_idx=col + 1) for row, values in enumerate((("구분", "지원금"), ("기업", "500만원")))
             for col, value in enumerate(values)]
    table = document.add_table(data=TableData(num_rows=2, num_cols=2, table_cells=cells), prov=prov(1, 140))
    table.meta = meta("table_quality", {"verdict": "TABLE_VALID", "reasons": []})
    failed = document.add_text(label=DocItemLabel.TEXT, text="보존된 표 text 자부담 20%", prov=prov(2, 60))
    failed.meta = meta("table_quality", {"verdict": "TABLE_QUALITY_FAILED", "reasons": ["grid_unproven"]})
    return document


SOURCE = ChunkSource("a" * 64, "PDF", "DOCLING_PDF", "b" * 64, {"route": "DOCLING_PDF"},
                     (("PBLN_1", "공고 하나"), ("PBLN_2", "공고 둘")))


class DocumentChunkingContractTests(unittest.TestCase):
    def test_docling_document_chunks_keep_structure_provenance_and_no_meta_text(self):
        chunks = chunk_document(sample_document(), SOURCE)
        texts = " ".join(chunk.embedding_text for chunk in chunks)
        # BOUNDARY: provenance meta는 FinalChunk metadata로만 가고 embedding text에 dict로 섞이지 않는다.
        self.assertNotIn("Contents/section0.xml", texts)
        self.assertNotIn("TABLE_QUALITY_FAILED", texts)
        # VALID TableItem과 text로 보존된 FAILED 표 영역이 모두 chunk에 남는다.
        for value in ("업력 3년 이하", "500만원", "자부담 20%"):
            self.assertIn(value, texts)
        # 본문 없이 이어지는 heading도 heading-only chunk로 남고 text가 비지 않는다.
        self.assertTrue(all(chunk.text.strip() for chunk in chunks))
        self.assertIn("빈 절", [chunk.text for chunk in chunks if chunk.heading_only])
        heading_chunk = next(chunk for chunk in chunks if "업력 3년" in chunk.text)
        self.assertEqual(heading_chunk.heading_path, ["지원대상", "업력 조건"])
        # 검색용 embedding_text는 공고명(MySQL 공고명) 다음 heading 경로다. 근거 본문 text에는 공고명을 넣지 않는다(IMP-001).
        self.assertTrue(heading_chunk.embedding_text.startswith(f"{heading_chunk.title}\n지원대상\n업력 조건\n"))
        self.assertTrue(all(chunk.embedding_text.startswith(chunk.title + "\n") for chunk in chunks))
        self.assertFalse(any(chunk.title in chunk.text for chunk in chunks))
        self.assertIn(heading_chunk.text, heading_chunk.embedding_text)
        self.assertTrue(all(chunk.token_count <= chunk.chunker_identity["max_tokens"] for chunk in chunks))
        # 공고 relation마다 FinalChunk가 있고, 공고명이 다르면 embedding 입력이 달라 content_key도 다르다.
        self.assertEqual({chunk.pblanc_id for chunk in chunks}, {"PBLN_1", "PBLN_2"})
        by_index = {}
        for chunk in chunks:
            by_index.setdefault(chunk.chunk_index, set()).add(chunk.content_key)
        self.assertTrue(all(len(keys) == 2 for keys in by_index.values()))
        same_title = chunk_document(sample_document(), dataclasses.replace(SOURCE, announcements=(("PBLN_1", "같은 공고"), ("PBLN_2", "같은 공고"))))
        self.assertEqual(len({chunk.content_key for chunk in same_title}), len(same_title) // 2)
        located = [entry for chunk in chunks for entry in chunk.provenance if entry.get("xml_path")]
        # 여러 page에 걸친 내용은 provenance 목록과 pages 집합으로 모든 위치를 유지한다.
        self.assertEqual({page for chunk in chunks for page in chunk.pages}, {1, 2})
        self.assertTrue(all(chunk.pages for chunk in chunks))
        self.assertEqual(located[0]["section"], "Contents/section0.xml")
        self.assertEqual([chunk.chunk_id for chunk in chunks], [chunk.chunk_id for chunk in chunk_document(sample_document(), SOURCE)])
        self.assertNotIn("embedding_text", chunks[0].payload())

    def test_chunk_identity_changes_with_tokenizer_size_policy_and_parser_result(self):
        contract = chunking_contract()
        identity = chunker_identity(contract)
        base = chunk_set_key("a" * 64, "b" * 64, identity, contract)

        def changed(mutate):
            other = copy.deepcopy(contract)
            mutate(other)
            return chunk_set_key("a" * 64, "b" * 64, chunker_identity(other), other)
        # tokenizer·max_tokens·chunking 정책·parser 결과가 바뀌면 chunk identity도 바뀐다.
        self.assertNotEqual(base, changed(lambda c: c["chunker"].update(max_tokens=256)))
        self.assertNotEqual(base, changed(lambda c: c["tokenizer"].update(revision="0" * 40)))
        self.assertNotEqual(base, changed(lambda c: c["chunker"].update(merge_peers=False)))
        # embedding_text context 정책이 바뀌면 re-index 전에 chunk identity가 바뀐다.
        self.assertNotEqual(base, changed(lambda c: c["chunker"].update(chunker_version=1, embedding_context="none")))
        self.assertNotEqual(base, chunk_set_key("a" * 64, "c" * 64, identity, contract))
        self.assertEqual(base, chunk_set_key("a" * 64, "b" * 64, chunker_identity(contract), contract))

    def test_contract_aligns_tokenizer_with_embedding_and_keeps_parse_identity_scoped(self):
        contract, parse_contract = chunking_contract(), parsing_contract()
        self.assertIn("forbidden", contract["representation"]["markdown_input"])
        self.assertEqual(contract["chunker"]["serializer"]["allowed_meta_names"], [])
        tokenizer = contract["tokenizer"]
        handoff = contract["embedding_handoff"]
        self.assertEqual((handoff["model_repo_id"], handoff["model_revision"]), (tokenizer["repo_id"], tokenizer["revision"]))
        model = next(m for m in parse_contract["dependencies"]["docling"]["model_artifacts"]["models"] if m["repo_id"] == tokenizer["repo_id"])
        self.assertEqual((model["resolved_snapshot"], model["scope"], model["folder"]),
                         (tokenizer["revision"], "chunking", tokenizer["artifact_folder"]))
        # chunking tokenizer를 추가해도 parse identity는 parsing 범위 파일만으로 계산돼 PDF·HWP parse_key가 바뀌지 않는다.
        self.assertNotIn(tokenizer["artifact_folder"], {folder for folder, _ in artifact_files(parse_contract, "parsing")})
        self.assertNotEqual(scoped_artifacts_sha256(parse_contract, "parsing"), scoped_artifacts_sha256(parse_contract, "chunking"))

    def test_hwp_converter_identity_failure_is_source_scoped_and_normal_key_unchanged(self):
        contract, version = parsing_contract(), "LibreOffice 1 | H2Orestart 2 | dockerfile 3"
        # BOUNDARY: CLI는 PipelineError만 source 단위로 격리하므로 변환기 오류가 그대로 새면 batch 전체가 멈춘다.
        with mock.patch("biz_aid_pipeline.parsing.hwp_pdf.converter_version",
                        side_effect=HwpConversionError("hwp_converter_unavailable")):
            with self.assertRaises(PipelineError) as raised:
                current_parse_key("a" * 64, "HWP", contract)
        self.assertEqual(str(raised.exception), "hwp_converter_identity_unavailable:hwp_converter_unavailable")
        with mock.patch("biz_aid_pipeline.parsing.hwp_pdf.converter_version", return_value=version):
            self.assertEqual(current_parse_key("a" * 64, "HWP", contract),
                             ("HWP_PDF_DOCLING", parse_key("a" * 64, "HWP_PDF_DOCLING", contract, version)))


if __name__ == "__main__":
    unittest.main()
