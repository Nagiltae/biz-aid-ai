import copy
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data-pipeline/src"))
from biz_aid_pipeline.candidates.question import choose_program, deterministic_mode
from biz_aid_pipeline.candidates.personalized import regional_ranking
from biz_aid_pipeline.config.settings import PipelineError
from biz_aid_pipeline.indexing.document_role import document_role
from biz_aid_pipeline.eligibility.service import output_schema
from biz_aid_pipeline.rag.service import rag_contract
from test_eligibility import evaluate, criterion, TARGET
from test_document_retrieval import CharEmbedder
from test_document_indexing import identity
from biz_aid_pipeline.indexing.embedder import indexing_contract
from biz_aid_pipeline.indexing.pipeline import index_chunks
from biz_aid_pipeline.retrieval.retriever import Retriever
from test_document_chunking import sample_document, SOURCE
from biz_aid_pipeline.chunking.chunker import chunk_document
from qdrant_client import QdrantClient, models


class BundleQualityTests(unittest.TestCase):
    def test_required_evidence_and_diagnostic_separate_empty_and_outside(self):
        schema = output_schema(["credit_score"], ["E1"], 15)
        self.assertEqual(schema["properties"]["criteria"]["items"]["properties"]["evidence_ids"]["minItems"], 1)
        for ids, text in (([], "empty=True outside_count=0"), (["E99"], "empty=False outside_count=1")):
            with self.assertLogs("biz_aid_pipeline.eligibility.service", level="WARNING") as logs:
                with self.assertRaisesRegex(PipelineError, "eligibility_invalid_evidence_id"):
                    evaluate([criterion("지원 요건", "MET", ["credit_score"], ids)])
            self.assertIn(text, logs.output[0])
        _, retriever = evaluate([criterion("지원 요건", "MET", ["credit_score"])])
        self.assertEqual(retriever.exclude_roles, ("FORM",))

    def test_form_filter_preserves_unknown_and_missing_in_all_modes(self):
        client, contract = QdrantClient(":memory:"), indexing_contract()
        embedder = CharEmbedder(identity(), 1024)
        chunks = chunk_document(sample_document(), SOURCE)
        index_chunks(chunks, SOURCE.source_sha256, embedder, client, contract)
        retriever = Retriever(embedder, client, contract)
        # 동일 텍스트에 FORM·UNKNOWN·역할 없는 기존 point를 붙여 필터를 실제로 검증한다.
        base = client.scroll(retriever.collection, limit=1, with_vectors=True)[0][0]
        points = []
        for number, role in enumerate(("FORM", "UNKNOWN", None), 1):
            payload = dict(base.payload, chunk_id=f"fixture-{number}")
            if role is not None:
                payload["document_role"] = role
            else:
                payload.pop("document_role", None)
            points.append(models.PointStruct(id=number, vector=base.vector, payload=payload))
        client.upsert(retriever.collection, points=points)
        for mode in ("dense", "sparse", "hybrid"):
            filtered = retriever.search("업력", mode, top_k=20, exclude_roles=("FORM",))
            ids = {item.chunk_id for item in filtered}
            self.assertNotIn("fixture-1", ids)
            self.assertTrue({"fixture-2", "fixture-3"}.issubset(ids))
            self.assertIn("fixture-1", {item.chunk_id for item in retriever.search("업력", mode, top_k=20)})

    def test_internal_policy_unknown_but_business_guidelines_remain_body(self):
        self.assertEqual(document_role("HWP", ["첨부 3. 대구테크노파크 전문가 수당지급 지침.hwp"]), "UNKNOWN")
        self.assertEqual(document_role("HWP", ["지원사업 운영지침.hwp"]), "BODY")

    def test_region_bonus_zero_local_rise_and_unrelated_not_boosted(self):
        spec = rag_contract()["personalized_ranking"]
        rows = [{"rank": 1, "rrf_score": .03, "jurisdiction_name": "중소벤처기업부"},
                {"rank": 2, "rrf_score": .0295, "jurisdiction_name": "경기도"},
                {"rank": 3, "rrf_score": .02, "jurisdiction_name": "경기도"}]
        ranked = regional_ranking(rows, "경기도", spec)
        self.assertEqual([r["original_rank"] for r in ranked], [2, 1, 3])
        self.assertEqual([r["region_bonus"] for r in ranked], [.001, 0, 0])
        for region in (None, "경기", "서울특별시"):
            self.assertEqual([r["original_rank"] for r in regional_ranking(rows, region, spec)], [1, 2, 3])
        self.assertEqual([r["original_rank"] for r in regional_ranking(rows, "경기도", dict(spec, region_bonus=0))], [1, 2, 3])

    def test_named_question_list_priority_and_ambiguous_llm(self):
        metadata = {"P1": {"pblanc_id": "P1", "name": "2026년 비즈플러스카드 지원사업"}}
        self.assertEqual(deterministic_mode("비즈플러스카드 지원요건 알려줘", metadata), "DOCUMENT_QA")
        self.assertEqual(deterministic_mode("비즈플러스카드 같은 금융 사업 추천", metadata), "SEARCH_LIST")
        self.assertIsNone(deterministic_mode("이 사업 알려줘", metadata))

    def test_selection_name_open_latest_tie_and_explicit_scope(self):
        rows = {pid: {"pblanc_id": pid, "name": "비즈플러스카드 지원사업", "source_created_at": "2026-01-01"}
                for pid in ("P1", "P2")}
        scope, choices = choose_program("비즈플러스카드 지원요건 알려줘", rows, date(2026, 10, 3))
        self.assertEqual(scope, ())
        self.assertEqual(len(choices), 2)
        rows["P2"].update(application_start_date=date(2026, 1, 1), application_end_date=date(2026, 12, 31))
        self.assertEqual(choose_program("비즈플러스카드 지원요건", rows, date(2026, 10, 3))[0], ("P2",))
        rows["P1"].update(rows["P2"], pblanc_id="P1", source_created_at="2026-02-01")
        self.assertEqual(choose_program("비즈플러스카드 지원요건", rows, date(2026, 10, 3))[0], ("P1",))
        self.assertEqual(choose_program("같은 질문", rows, selected_id="P2")[0], ("P2",))
        with self.assertRaisesRegex(PipelineError, "query_program_not_found"):
            choose_program("질문", rows, selected_id="P3")

    def test_payload_only_update_preserves_vectors_and_v1_boundary(self):
        from biz_aid_pipeline.indexing.role_update import update_internal_roles
        client = QdrantClient(":memory:")
        client.create_collection("bizaid_v2_fixture", vectors_config=models.VectorParams(size=2, distance=models.Distance.COSINE))
        client.upsert("bizaid_v2_fixture", points=[models.PointStruct(id=1, vector=[1., 0.], payload={"source_sha256": "a", "source_format": "HWP", "document_role": "BODY", "chunk_id": "fixed"})])
        result = update_internal_roles(client, "bizaid_v2_fixture", {"a": ["전문가 수당지급 지침.hwp"]}, True)
        self.assertEqual(result["changed_point_count"], 1)
        self.assertTrue(result["changes"][0]["identity_vector_payload_unchanged"])
        self.assertEqual(update_internal_roles(client, "bizaid_v2_fixture", {"a": ["전문가 수당지급 지침.hwp"]}, True)["changed_point_count"], 0)
        with self.assertRaisesRegex(PipelineError, "role_update_v2_only"):
            update_internal_roles(client, "bizaid_chunks_v1_fixture", {})

    def test_runtime_selection_does_not_search_and_choice_scopes_qa(self):
        from biz_aid_pipeline.runtime import ServiceRuntime
        from biz_aid_pipeline.candidates.service import ProgramCandidateRepository
        from test_program_candidates import row, engine_with
        from test_rag_answer import FakeRetriever, FakeProvider, result
        from biz_aid_pipeline.rag.llm import LlmResponse
        import json
        rows = [dict(row(pid), name="비즈플러스카드 지원사업") for pid in ("PBLN_000000000119801", "PBLN_000000000119802")]
        repository = ProgramCandidateRepository(engine_with(rows))
        runtime = ServiceRuntime.__new__(ServiceRuntime)
        runtime.repository = repository
        class Provider:
            name, model = "fake", "fake"
            def generate(self, request):
                self.schema = request.output_schema
                return LlmResponse(json.dumps({"request_mode": "SEARCH_LIST", "categories": [], "targets": [],
                    "currently_open_requested": False, "unapplied_constraints": []}), "fake", "fake", 0.)
        provider = Provider()
        runtime.provider = provider
        runtime.retriever = lambda: self.fail("동점 후보 선택 전에 검색하면 안 됨")
        output = runtime.answer_query("비즈플러스카드 지원요건 알려줘", date(2026, 10, 3))
        self.assertEqual(output["status"], "SELECTION_REQUIRED")
        self.assertEqual(provider.schema["properties"]["request_mode"]["enum"], ["DOCUMENT_QA"])
        target = "PBLN_000000000119802"
        fake = FakeRetriever([result(1, "chunk", target, "지원 요건 근거")])
        runtime.provider = FakeProvider({"answer": "지원 요건", "evidence_ids": ["E1"], "insufficient_evidence": False})
        runtime.retriever = lambda: fake
        chosen = runtime.answer_query("비즈플러스카드 지원요건 알려줘", selected_pblanc_id=target)
        self.assertEqual(chosen["selected_pblanc_id"], target)
        self.assertEqual({item["pblanc_id"] for item in chosen["citations"]}, {target})
        self.assertEqual(fake.exclude_roles, ("FORM",))
