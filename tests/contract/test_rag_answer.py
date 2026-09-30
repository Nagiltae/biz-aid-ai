import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data-pipeline/src"))

from biz_aid_pipeline.rag.llm import LlmResponse
from biz_aid_pipeline.rag.service import RagService
from biz_aid_pipeline.retrieval.retriever import SearchResult


def result(rank, chunk_id, pblanc_id, text, pages=(3,)):
    return SearchResult(rank=rank, mode="hybrid", score=0.03, chunk_id=chunk_id, pblanc_id=pblanc_id, title=f"지원사업 공고 {rank}",
                        text=text, heading_path=["2. 지원 요건"], source_sha256="a" * 64, source_format="PDF", route="DOCLING_PDF",
                        parse_key="b" * 64, chunk_set_key="c" * 64, chunk_index=rank, pages=list(pages),
                        provenance=[{"page": pages[0] if pages else None, "bbox_pt": [1, 2, 3, 4]}], embedding_key="e" * 64)


class FakeRetriever:
    def __init__(self, results):
        self.results, self.calls = results, []

    def search(self, query, mode, top_k, pblanc_ids=None):
        self.calls.append((query, mode, top_k) if pblanc_ids is None else (query, mode, top_k, tuple(pblanc_ids)))
        return self.results


class FakeProvider:
    name, model = "fake", "fake-1"

    def __init__(self, output):
        self.output, self.requests = output, []

    def generate(self, request):
        self.requests.append(request)
        return LlmResponse(json.dumps(self.output, ensure_ascii=False), self.name, self.model, 0.1)


RESULTS = [result(1, "chunk-1", "PBLN_1", "업력 6개월 이상 개인사업자"), result(2, "chunk-2", "PBLN_2", "보증한도 900만원")]


class RagAnswerContractTests(unittest.TestCase):
    def test_citations_are_resolved_by_the_application_from_retrieved_results(self):
        retriever = FakeRetriever(RESULTS)
        provider = FakeProvider({"answer": "보증한도는 900만원입니다.", "evidence_ids": ["E2"], "insufficient_evidence": False})
        answer = RagService(retriever, provider).answer("보증한도는?")
        # 적재·평가 baseline과 같은 hybrid top_k 5로 검색한다.
        self.assertEqual(retriever.calls, [("보증한도는?", "hybrid", 5)])
        self.assertEqual((answer.status, answer.used_evidence_ids), ("ANSWERED", ["E2"]))
        citation = answer.citations[0]
        self.assertEqual((citation.chunk_id, citation.pblanc_id, citation.pages, citation.rank), ("chunk-2", "PBLN_2", [3], 2))
        # BOUNDARY: LLM에는 evidence id와 읽을 내용만 가고 식별자·원본 provenance는 가지 않는다.
        prompt = provider.requests[0].user
        self.assertIn("[E2]", prompt)
        for leaked in ("chunk-2", "PBLN_2", "a" * 64, "b" * 64, "bbox_pt"):
            self.assertNotIn(leaked, prompt)

    def test_unknown_evidence_ids_never_become_citations(self):
        provider = FakeProvider({"answer": "지원 가능합니다.", "evidence_ids": ["E9", "chunk-1"], "insufficient_evidence": False})
        answer = RagService(FakeRetriever(RESULTS), provider).answer("지원 가능한가?")
        # 유효한 근거가 하나도 없으면 답을 근거 기반으로 내보내지 않는다.
        self.assertEqual((answer.status, answer.citations, answer.rejected_evidence_ids), ("INSUFFICIENT_EVIDENCE", [], ["E9", "chunk-1"]))
        self.assertEqual(answer.discarded_answer, "지원 가능합니다.")
        mixed = RagService(FakeRetriever(RESULTS), FakeProvider(
            {"answer": "업력 6개월 이상입니다.", "evidence_ids": ["E1", "E7"], "insufficient_evidence": False})).answer("업력?")
        self.assertEqual(([c.chunk_id for c in mixed.citations], mixed.rejected_evidence_ids), (["chunk-1"], ["E7"]))

    def test_insufficient_evidence_returns_fixed_message_without_citations(self):
        provider = FakeProvider({"answer": "근거가 없습니다.", "evidence_ids": ["E1"], "insufficient_evidence": True})
        answer = RagService(FakeRetriever(RESULTS), provider).answer("신청 마감일은?")
        self.assertEqual((answer.status, answer.answer, answer.citations), ("INSUFFICIENT_EVIDENCE", "제공된 공고문 근거만으로는 확인할 수 없습니다.", []))
        empty = RagService(FakeRetriever([]), FakeProvider(
            {"answer": "없음", "evidence_ids": [], "insufficient_evidence": True})).answer("아무 질문")
        self.assertEqual((empty.status, empty.retrieved), ("INSUFFICIENT_EVIDENCE", []))

    def test_candidate_scope_short_circuits_when_empty_and_rejects_leaks(self):
        from biz_aid_pipeline.config.settings import PipelineError
        retriever, provider = FakeRetriever(RESULTS), FakeProvider({"answer": "x", "evidence_ids": ["E1"], "insufficient_evidence": False})
        empty = RagService(retriever, provider).answer("보증한도는?", candidate_pblanc_ids=())
        # BOUNDARY: 정형 후보가 없으면 검색·LLM 호출 없이 고정 결과를 돌려준다.
        self.assertEqual((empty.status, empty.candidate_count, retriever.calls, provider.requests), ("NO_CANDIDATES", 0, [], []))
        scoped = RagService(retriever, provider).answer("보증한도는?", candidate_pblanc_ids=("PBLN_1", "PBLN_2"))
        self.assertEqual((retriever.calls[-1], scoped.candidate_count), (("보증한도는?", "hybrid", 5, ("PBLN_1", "PBLN_2")), 2))
        with self.assertRaisesRegex(PipelineError, "retrieval_scope_violation"):
            RagService(FakeRetriever(RESULTS), provider).answer("보증한도는?", candidate_pblanc_ids=("PBLN_1",))


if __name__ == "__main__":
    unittest.main()
