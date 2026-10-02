import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data-pipeline/src"))

from biz_aid_pipeline.chunking.chunker import chunking_contract
from biz_aid_pipeline.indexing.document_role import ROLES, document_role
from biz_aid_pipeline.indexing.embedder import indexing_contract
from biz_aid_pipeline.parsing.models import PARSE_KEY_INPUTS


class DocumentRoleTests(unittest.TestCase):
    def test_filename_cues_with_form_first_priority(self):
        self.assertEqual(document_role("DOCX", ["(워드양식) 2026년도 연구실 안전관리 컨설팅 신청양식.docx"]), "FORM")
        self.assertEqual(document_role("XLSX", ["2026 통번역 서포터즈 명단(게시용)_260123.xlsx"]), "LIST")
        self.assertEqual(document_role("DOCX", ["서울시 소상공인 온라인 유통 MD 상담 지원 공고문.docx"]), "BODY")
        # 양식 단서가 본문 단서보다 먼저다(공고문과 양식이 한 이름에 함께 있으면 양식으로 본다).
        self.assertEqual(document_role("ZIP", ["과정별 공고문 및 제출서류 양식_수정.zip"]), "FORM")
        self.assertEqual(document_role("XLS", ["별첨1_(양식) 직접참여인력 및 이해관계자 리스트_26인턴십.xls"]), "FORM")
        # 공백·대소문자 차이는 같은 단서로 본다.
        self.assertEqual(document_role("DOCX", ["Application FORM.docx"]), "FORM")
        self.assertEqual(document_role("DOCX", ["신 청 서.docx"]), "FORM")

    def test_submission_documents_cue_needs_a_qualifier(self):
        # 2026-10-03 규칙 개정: "제출서류" 단독은 양식 단서가 아니다. 안내·기준은 본문, 목록·체크리스트는 목록이다.
        self.assertEqual(document_role("HWP", ["【붙임1】 K-브랜드분쟁 대응전략 지원사업 선정심사 기준 및 제출 서류 안내.hwp"]), "BODY")
        self.assertEqual(document_role("HWP", ["2026 수출입 애로 중소기업 바우처 지원사업 제출서류 체크리스트.hwp"]), "LIST")
        self.assertEqual(document_role("PDF", ["0. 제출서류 목록(2026년 개정).pdf"]), "LIST")
        self.assertEqual(document_role("HWPX", ["[붙임 2] 신청기업 제출서류.hwpx"]), "UNKNOWN")
        # 다른 양식 단서가 함께 있으면 양식 우선순위는 그대로다.
        self.assertEqual(document_role("HWP", ["(프로그램 2) 신청서 및 제출서류 서식_R&D 연계 신속화.hwp"]), "FORM")
        # 새 양식 단서. 심사 기준이 담긴 평가표는 양식으로 보지 않는다.
        for name in ("붙임 1. 결과(실적)보고서 양식_기업명.hwp", "수출 패키지 지원사업 사업결과보고서.hwpx",
                     "2. (필수제출) 전시품목 상세서(워드).docx", "맞춤형 AllSET 컨설팅_만족도조사서.hwp",
                     "[붙임3]기업현장애로+컨설팅+전문가+프로필.hwp"):
            self.assertEqual(document_role("HWP", [name]), "FORM", name)
        self.assertEqual(document_role("HWP", ["[별지 제2호] 평가표.hwp"]), "UNKNOWN")

    def test_format_defaults_and_disagreement(self):
        # 이미지는 포스터·공고 캡처라 단서가 없으면 본문으로 본다. 다른 형식은 단서가 없으면 미상이다.
        self.assertEqual(document_role("PNG", ["컨설팅_001.png"]), "BODY")
        self.assertEqual(document_role("JPEG", []), "BODY")
        self.assertEqual(document_role("XLSX", ["sheet.xlsx"]), "UNKNOWN")
        self.assertEqual(document_role("DOCX", [None, ""]), "UNKNOWN")
        # 같은 원본에 붙은 파일명이 서로 다른 종류를 가리키면 단정하지 않는다.
        self.assertEqual(document_role("XLSX", ["신청서.xlsx", "참여기업 명단.xlsx"]), "UNKNOWN")
        self.assertIn(document_role("PDF", ["모집 공고.pdf"]), ROLES)

    def test_role_is_outside_every_identity_input(self):
        # BOUNDARY: 출처 종류를 기록해도 기존 PDF·HWP·HWPX의 parse_key·chunk_set_key·embedding_key가 바뀌면 안 된다.
        contract, chunking = indexing_contract(), chunking_contract()
        self.assertEqual(contract["document_role"]["values"], list(ROLES))
        self.assertNotIn("document_role", PARSE_KEY_INPUTS)
        self.assertNotIn("document_role", chunking["identity"]["chunk_set_key_inputs"])
        self.assertNotIn("document_role", contract["identity"]["embedding_key_inputs"])
        self.assertNotIn("document_role", str(chunking["chunker"]) + str(contract["embedding"]))
        # 출처 종류 규칙을 바꿔도 해시되는 계약 부분(chunker·embedding)은 그대로다.
        changed = copy.deepcopy(contract)
        changed["document_role"]["filename_cues"]["FORM"].append("새단서")
        changed["document_role"]["qualified_cues"].append({"cue": "새단서", "role": "BODY", "with_any": ["안내"]})
        self.assertEqual(changed["embedding"], contract["embedding"])
        self.assertIn("not used for search ranking", contract["document_role"]["ranking"])


if __name__ == "__main__":
    unittest.main()
