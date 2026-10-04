import unittest
from dataclasses import replace
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data-pipeline/src"))

from biz_aid_pipeline.rag.service import readable_evidence, build_context
from biz_aid_pipeline.candidates.discovery import business_identity, ProgramDiscoveryService
from test_rag_answer import result
from unittest.mock import Mock


class Bundle4QualityTests(unittest.TestCase):
    def test_table_context_flat_cells_preserves_values_and_identity(self):
        raw = "등급, 1 = A. 등급, 2 = 32,760원. 기간, 1 = 최대 12개월. 기간, 2 = B"
        output = readable_evidence(raw)
        for token in ("A", "32,760원", "최대 12개월", "B"):
            self.assertIn(token, output)
        self.assertIn("행·병합 구조는 추정하지 않음", output)
        plain = "지원대상은 다음과 같다. 등급, 1 = A. 등급, 2 = B"
        self.assertEqual(readable_evidence(plain), plain)
        item = result(1, "fixed-id", "P", raw)
        context, index = build_context([item])
        self.assertIs(index["E1"], item)
        self.assertEqual(item.text, raw)
        self.assertIn(output, context)

    def test_business_dedup_keeps_first_rank_and_regional_businesses_separate(self):
        row = {"pblanc_id":"A","name":"2026년 1차 수출기업 해외지사화 모집 공고", "jurisdiction_name":"산업통상부", "category":"수출", "target":"중소기업"}
        other = dict(row,pblanc_id="B",name="2026년 2차 수출기업 해외지사화 모집 공고")
        self.assertEqual(business_identity(row), business_identity(other))
        # EXCEPTION: 2차전지의 차는 모집 차수가 아니다. 산업명은 삭제하지 않는다.
        self.assertNotEqual(business_identity(dict(row,name="2차전지 해외지사화 지원사업")),
                            business_identity(dict(other,name="전지 해외지사화 지원사업")))
        self.assertNotEqual(business_identity(dict(row,name="[서울] 해외지사화 지원 모집 공고")),business_identity(dict(other,name="[부산] 해외지사화 지원 모집 공고")))
        repository, retriever = Mock(), Mock()
        first, second = result(1,"a","A","a"),result(2,"b","B","b")
        retriever.search_programs.return_value = [first,first,second]
        fields={"executing_org_name":None,"application_start_date":None,"application_end_date":None,"application_period_raw":None,"announcement_url":None}
        repository.program_metadata.return_value={"A":dict(row,**fields),"B":dict(other,**fields)}
        from biz_aid_pipeline.rag.service import rag_contract
        response=ProgramDiscoveryService(repository,retriever,rag_contract()).discover("질문",("A","B"))
        self.assertEqual([v["pblanc_id"] for v in response],["A"])
        self.assertEqual(response[0]["rrf_score"],first.score)
