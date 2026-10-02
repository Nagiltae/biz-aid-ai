import io
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data-pipeline/src"))

from PIL import Image

from biz_aid_pipeline.chunking.chunker import item_provenance
from biz_aid_pipeline.parsing import image_ocr
from biz_aid_pipeline.parsing.image_ocr import ImageOcrError, merge_tile_lines, tile_ranges
from biz_aid_pipeline.parsing.models import ParseRequest, parse_identity, parsing_contract
from biz_aid_pipeline.parsing.pdf_ocr import OcrLine
from biz_aid_pipeline.parsing.router import parse_document

SPEC = {"tile_height_px": 2000, "tile_overlap_ratio": 0.12}


def png(width, height, mode="RGB"):
    stream = io.BytesIO()
    Image.new(mode, (width, height), "white").save(stream, "PNG")
    return stream.getvalue()


class FakeModel:
    """타일마다 정해 둔 줄을 PaddleX 출력 모양으로 돌려준다. box는 타일 안 좌표다."""

    def __init__(self, per_tile):
        self.per_tile, self.calls = per_tile, []

    def predict(self, tile):
        self.calls.append(tile.shape)
        texts, scores, boxes = zip(*self.per_tile[len(self.calls) - 1]) if self.per_tile[len(self.calls) - 1] else ((), (), ())
        return [{"rec_texts": list(texts), "rec_scores": list(scores), "rec_boxes": list(boxes)}]


def parse(raw, detected, model):
    import hashlib
    sha = hashlib.sha256(raw).hexdigest()
    with mock.patch.object(image_ocr, "pipeline", return_value=model), \
            mock.patch.object(image_ocr, "ocr_identity", return_value="paddlex test OCR"):
        return parse_document(ParseRequest(sha, detected, len(raw)), raw, parsing_contract())


class ImageOcrTests(unittest.TestCase):
    def test_vertical_tiles_overlap_and_align_the_last_tile(self):
        self.assertEqual(tile_ranges(1500, SPEC), [(0, 1500)])
        self.assertEqual(tile_ranges(2000, SPEC), [(0, 2000)])
        tiles = tile_ranges(4434, SPEC)
        # 2,000px 타일, 240px(12%) 겹침, 마지막 타일은 아래 끝에 맞춘다.
        self.assertEqual(tiles, [(0, 2000), (1760, 3760), (2434, 4434)])
        self.assertTrue(all(end - start == 2000 for start, end in tiles))
        self.assertTrue(all(tiles[i][1] > tiles[i + 1][0] for i in range(len(tiles) - 1)))

    def test_overlap_lines_are_kept_once_by_center_ownership(self):
        tiles = [(0, 2000), (1760, 3760)]
        # 경계(1,880) 근처 같은 줄이 두 타일에 모두 잡혔다. 원본 좌표 기준이다.
        same_top = OcrLine(0, [10, 1850, 300, 1890], "지원 대상", 0.9)
        same_bottom = OcrLine(0, [10, 1851, 300, 1891], "지원 대상", 0.8)
        only_top = OcrLine(0, [10, 100, 300, 140], "공고", 0.99)
        cut_in_top = OcrLine(0, [10, 1985, 300, 2000], "신청", 0.4)   # 위 타일 아래 끝에서 잘린 줄
        full_in_bottom = OcrLine(0, [10, 1985, 300, 2025], "신청 방법", 0.95)
        lines = merge_tile_lines([[only_top, same_top, cut_in_top], [same_bottom, full_in_bottom]], tiles)
        self.assertEqual([(line.page, line.text) for line in lines], [(1, "공고"), (1, "지원 대상"), (2, "신청 방법")])

    def test_image_document_keeps_original_pixel_bbox_and_tile_pages(self):
        raw = png(1000, 4434)
        # 타일당 50자를 넘는 줄(공백 제외)을 하나씩 둔다. 적으면 문서 text Gate에서 OCR_REQUIRED가 된다(다음 test).
        model = FakeModel([[("2026년 지역 중소기업 해외시장 진출 지원사업 참여기업 모집 공고 신청 자격과 지원 내용 및 신청 방법을 아래와 같이 안내합니다", 0.97, [20, 50, 900, 90])],
                           [("지원 대상은 도내 중소기업 및 소상공인이며 기업당 최대 720만원의 해외 물류비와 인증 비용을 지원하고 신청 기간은 2026년 12월까지입니다", 0.91, [20, 300, 900, 340])],
                           [("문의처는 042-000-0000 담당 부서이며 제출 서류와 선정 기준 등 기타 자세한 사항은 함께 게시한 공고문 본문을 반드시 참조하시기 바랍니다", 0.88, [20, 1900, 900, 1940])]])
        result = parse(raw, "PNG", model)
        self.assertEqual((result.route, result.status, result.unit_count), ("IMAGE_OCR", "PARSED", 3))
        # 폭은 그대로(1,000px) 타일 높이 2,000px로 세 번 읽었다.
        self.assertEqual(model.calls, [(2000, 1000, 3), (2000, 1000, 3), (2000, 1000, 3)])
        document = result.document
        self.assertEqual({page.size.width for page in document.pages.values()}, {1000})
        self.assertEqual({page.size.height for page in document.pages.values()}, {4434})
        second = document.texts[1]
        entry = item_provenance(second, document)
        # 두 번째 타일(시작 y 1,760)의 줄은 원본 좌표 y 2,060~2,100으로 남는다.
        self.assertEqual((entry["page"], entry["bbox_pt"]), (2, [20.0, 2060.0, 900.0, 2100.0]))
        meta = second.meta.get_custom_part()["bizaid__ocr"]
        self.assertEqual((meta["unit"], meta["tile_y_px"], meta["bbox_px"]), ("px", [1760, 3760], [20.0, 2060.0, 900.0, 2100.0]))
        self.assertEqual(entry["ocr_confidence"], 0.91)
        self.assertEqual(result.ocr["tiles_y_px"], [[0, 2000], [1760, 3760], [2434, 4434]])
        self.assertEqual(result.warnings["IMAGE_OCR_APPLIED"], 3)

    def test_too_little_text_is_ocr_required_and_limits_fail_the_document(self):
        result = parse(png(800, 600), "PNG", FakeModel([[("로고", 0.99, [0, 0, 100, 30])]]))
        # 타일당 평균 글자 수가 기준 이하이면 적재하지 않는다(PDF OCR과 같은 문서 text Gate).
        self.assertEqual((result.status, result.warnings.get("OCR_TEXT_INSUFFICIENT")), ("OCR_REQUIRED", 1))
        contract = parsing_contract()
        with mock.patch.dict(contract["image_ocr"], {"max_total_pixels": 100}):
            raw = png(20, 20)
            import hashlib
            failed = parse_document(ParseRequest(hashlib.sha256(raw).hexdigest(), "PNG", len(raw)), raw, contract)
        self.assertEqual((failed.status, failed.failure_code), ("PARSE_FAILED", "image_pixels_exceeded"))
        # 형식이 다르거나 열 수 없는 byte는 OCR을 부르지 않고 실패로 남긴다.
        model = FakeModel([])
        self.assertEqual(parse(png(10, 10), "JPEG", model).failure_code, "image_format_mismatch")
        self.assertEqual(parse(b"not an image at all", "PNG", model).failure_code[:20], "image_decode_failed:")
        self.assertEqual(model.calls, [])
        # 투명 PNG도 RGB로 읽는다.
        self.assertEqual(parse(png(50, 50, "RGBA"), "PNG", FakeModel([[]])).status, "OCR_REQUIRED")

    def test_parse_key_scope_has_ocr_inputs_only(self):
        identity = parse_identity("0" * 64, "IMAGE_OCR", parsing_contract())
        present = {key for key, value in identity.items() if value is not None}
        self.assertEqual(present, {"source_sha256", "route", "normalizer_version", "docling_core_version", "model_artifacts_sha256",
                                   "paddlepaddle_version", "paddlex_version", "image_ocr_version", "image_ocr_config_sha256"})
        # Docling layout·표 engine identity는 넣지 않는다.
        for key in ("docling_version", "docling_parse_version", "docling_ibm_models_version", "pipeline_config_sha256", "converter_version"):
            self.assertIsNone(identity[key])
        # 기존 route identity에는 이미지 전용 key가 생기지 않는다(기존 parse_key 보존).
        self.assertNotIn("image_ocr_version", parse_identity("0" * 64, "HWPX_DOCLING_ADAPTER", parsing_contract()))


if __name__ == "__main__":
    unittest.main()
