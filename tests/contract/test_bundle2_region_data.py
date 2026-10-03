import copy
import dataclasses
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data-pipeline/src"))
sys.path.insert(0, str(ROOT / "tests/contract"))
from biz_aid_pipeline.candidates.region import program_regions, region_allowed
from biz_aid_pipeline.candidates.service import ProgramCandidateFilter, ProgramCandidateRepository
from biz_aid_pipeline.ingestion.normalizer import period, normalize
from biz_aid_pipeline.indexing.maintenance import prune_closed
from biz_aid_pipeline.indexing.pipeline import index_chunks
from biz_aid_pipeline.indexing.embedder import indexing_contract
from biz_aid_pipeline.config.settings import PipelineError
from qdrant_client import QdrantClient, models
from test_program_candidates import row, engine_with
from test_document_indexing import FakeEmbedder, identity
from test_document_chunking import sample_document, SOURCE
from biz_aid_pipeline.chunking.chunker import chunk_document


class Bundle2Tests(unittest.TestCase):
    def test_title_regions_owner_precedence_and_fail_open(self):
        self.assertEqual(program_regions("[부산ㆍ울산ㆍ경남] 공동사업", "경상남도")[1], "TITLE_REGION")
        self.assertTrue(region_allowed("부산광역시", "[부산ㆍ울산ㆍ경남] 공동사업", "경상남도"))
        self.assertFalse(region_allowed("서울특별시", "[인천] 사업", "중소벤처기업부"))
        self.assertTrue(region_allowed("충청북도", "[대전ㆍ충청] 사업", "중소벤처기업부"))
        self.assertTrue(region_allowed("전북특별자치도", "[호남권] 사업", "중소벤처기업부"))
        self.assertFalse(region_allowed("서울특별시", "[비수도권] 사업", "중소벤처기업부"))
        self.assertTrue(region_allowed("서울특별시", "[알수없음] 사업", "중소벤처기업부"))
        self.assertTrue(region_allowed("서울특별시", "[인천ㆍ외국] 사업", "중소벤처기업부"))
        self.assertFalse(region_allowed("서울특별시", "[서울] 제목오류", "인천광역시"))

    def test_candidate_title_override_survives_old_not_in_and_null_owner(self):
        rows = [dict(row("MULTI", jurisdiction="경상남도"), name="[부산ㆍ울산ㆍ경남] 공동사업"),
                dict(row("INC", jurisdiction="중소벤처기업부"), name="[인천] 사업"), row("NATIONAL", jurisdiction=None)]
        repository = ProgramCandidateRepository(engine_with(rows))
        result = repository.find(ProgramCandidateFilter(company_region="부산광역시", exclude_jurisdictions=("경상남도",)))
        self.assertEqual(result.pblanc_ids, ("MULTI", "NATIONAL"))
        self.assertEqual(result.region_basis, {"TITLE_REGION": 1, "NATIONWIDE_OR_UNMAPPED": 1})

    def test_dates_explicit_formats_and_unknown_preserve_raw_fingerprint(self):
        for raw in ("2026-1-2 ~ 2026-10-3", "2026.01.02 ~ 2026.10.03", "2026/01/02 ～ 2026/10/03", "2026년 1월 2일 ~ 2026년 10월 3일"):
            self.assertEqual(period(raw), (date(2026, 1, 2), date(2026, 10, 3), "DATE_RANGE"))
            value = normalize({"pblancId": "PBLN_TEST", "reqstBeginEndDe": raw})
            self.assertEqual(value.content["application_period_raw"], raw)
            self.assertEqual(value.source_fingerprint, normalize(value.source_payload).source_fingerprint)
        for raw in ("예산 소진시까지", "매월 10일 18:00까지", "2026.01.01 ~ 추후 공지"):
            self.assertEqual(period(raw)[2], "FREE_TEXT")
        self.assertEqual(period("2026.02.30 ~ 2026.10.01")[2], "INVALID_DATE_RANGE")
        self.assertEqual(period("2026.10.02 ~ 2026.10.01")[2], "INVALID_DATE_RANGE")

    def test_snapshot_required_before_closed_only_delete_and_v1_rejected(self):
        client = QdrantClient(":memory:")
        name = "bizaid_v2_fixture"
        client.create_collection(name, vectors_config=models.VectorParams(size=2, distance=models.Distance.COSINE))
        client.upsert(name, points=[models.PointStruct(id=i, vector=[1., 0.], payload={"pblanc_id": pid}) for i, pid in enumerate(("CLOSED", "UNKNOWN", "OPEN"))])
        with self.assertRaisesRegex(PipelineError, "snapshot_not_verified"):
            prune_closed(client, name, ("CLOSED",), lambda *_: {"verified": False}, True)
        self.assertEqual(client.count(name).count, 3)
        result = prune_closed(client, name, ("CLOSED",), lambda *_: {"verified": True}, True)
        self.assertEqual((result["deleted_points"], result["points_after"]), (1, 2))
        self.assertEqual(prune_closed(client, name, ("CLOSED",), lambda *_: self.fail("빈 대상에 백업 불필요"), True)["deleted_points"], 0)
        with self.assertRaisesRegex(PipelineError, "v2_only"):
            prune_closed(client, "bizaid_chunks_v1_fixture", (), None, True)

    def test_new_document_admission_whole_source_no_embedding_and_existing_untouched(self):
        client, contract = QdrantClient(":memory:"), copy.deepcopy(indexing_contract())
        embedder = FakeEmbedder(identity(), 1024)
        chunks = chunk_document(sample_document(), SOURCE)
        contract["new_document_admission"]["max_document_points_per_program"] = 1
        result = index_chunks(chunks, SOURCE.source_sha256, embedder, client, contract, namespace="v2")
        self.assertEqual(result["status"], "SKIPPED_INDEX_POLICY")
        self.assertEqual(embedder.calls, [])
        self.assertEqual(client.count(result["collection"]).count, 0)
        contract["new_document_admission"]["max_document_points_per_program"] = 200
        contract["new_document_admission"]["max_reference_points_per_program"] = 1
        result = index_chunks(chunks, SOURCE.source_sha256, embedder, client, contract, namespace="v2", filenames=("산업분류 해설서.pdf",))
        self.assertEqual(result["status"], "SKIPPED_INDEX_POLICY")
        good = index_chunks(chunks, SOURCE.source_sha256, embedder, client, contract, namespace="v2", filenames=("공고문.pdf",))
        self.assertEqual(good["status"], "INDEXED")
        contract["new_document_admission"]["max_document_points_per_program"] = 1
        again = index_chunks(chunks, SOURCE.source_sha256, embedder, client, contract, namespace="v2")
        self.assertEqual(again["status"], "INDEXED")
        self.assertEqual(again["source_points"], good["source_points"])

    def test_ai_named_outside_region_kept_with_warning_but_list_scoped(self):
        from biz_aid_pipeline.runtime import ServiceRuntime
        from biz_aid_pipeline.candidates.natural import NaturalFilterResult
        from test_rag_answer import FakeProvider, FakeRetriever, result
        from biz_aid_pipeline.candidates.question import choose_program
        repository = ProgramCandidateRepository(engine_with([dict(row("PBLN_000000000119801",jurisdiction="인천광역시"),name="비즈플러스카드 지원사업"),row("PBLN_000000000119802",jurisdiction="서울특별시")]))
        runtime = ServiceRuntime.__new__(ServiceRuntime)
        runtime.repository = repository
        runtime.provider = FakeProvider({"answer": "공고 조건", "evidence_ids": ["E1"], "insufficient_evidence": False})
        fake = FakeRetriever([result(1,"chunk","PBLN_000000000119801","공고 조건")])
        runtime.retriever = lambda: fake
        extraction = NaturalFilterResult("DOCUMENT_QA", ProgramCandidateFilter(), {}, {}, [], [], None)
        with patch("biz_aid_pipeline.candidates.natural.NaturalLanguageFilterService.extract", return_value=extraction):
            answer = runtime.answer_query("비즈플러스카드 지원요건", company_region="서울특별시")
        self.assertEqual(answer["selected_pblanc_id"], "PBLN_000000000119801")
        self.assertEqual(answer["region_warning"], "기업 지역과 다른 지역 공고입니다")
        self.assertFalse(answer["region_filter_applied"])
        self.assertEqual(repository.find(ProgramCandidateFilter(company_region="서울특별시")).pblanc_ids,("PBLN_000000000119802",))
        self.assertEqual(len(repository.find(ProgramCandidateFilter()).pblanc_ids),2)

    def test_reference_share_admission_is_program_scoped_and_whole_source(self):
        from biz_aid_pipeline.indexing.admission import admission_reasons
        from types import SimpleNamespace
        from unittest.mock import Mock
        client = Mock()
        client.count.return_value.count = 10
        chunks = [SimpleNamespace(pblanc_id="REFERENCE", source_sha256="sha") for _ in range(40)]
        spec = indexing_contract()["new_document_admission"]
        reasons = admission_reasons(chunks, ("가이드북.pdf",), client, "fixture", spec)
        self.assertEqual(reasons[0]["reason"], "reference_point_share")
        self.assertEqual(reasons[0]["share"], .8)
        request_filter = client.count.call_args.kwargs["count_filter"]
        self.assertEqual(request_filter.must[0].match.value, "REFERENCE")
        client.count.return_value.count = 100
        self.assertEqual(admission_reasons(chunks, ("가이드북.pdf",), client, "fixture", spec), [])
        self.assertEqual(admission_reasons(chunks, ("공고문.pdf",), client, "fixture", spec), [])
