import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data-pipeline/src"))

from biz_aid_pipeline.parsing.models import image_ocr_config_sha256, parse_identity, parsing_contract

# 2026-10-04 IMP-026 적용 직전 값. 이미 적재된 DOCX·PPTX·이미지 point의 parse_key 입력이라 바뀌면 안 된다.
OFFICE_CONFIG_SHA256 = "a060f27fc504eac0cfd74a88d8ab42c54b26b02595fdd8d59530d0ec29915c1b"
IMAGE_OCR_CONFIG_SHA256 = "af7f615736e5bee7ca799b23ed311c2aea0829ca1b2a4ca45f71b5d745db08bb"


def office_sha(contract):
    return parse_identity("0" * 64, "DOCLING_DOCX", contract)["office_config_sha256"]


class ConfigIdentityTests(unittest.TestCase):
    def test_existing_keys_are_unchanged(self):
        contract = parsing_contract()
        self.assertEqual(office_sha(contract), OFFICE_CONFIG_SHA256)
        self.assertEqual(image_ocr_config_sha256(contract), IMAGE_OCR_CONFIG_SHA256)

    def test_description_edits_in_live_sections_do_not_change_keys(self):
        contract = copy.deepcopy(parsing_contract())
        contract["office"]["converter"] = "설명 문구만 바꾼 경우"
        contract["office"]["pages"] += " (wording)"
        contract["image_ocr"]["tiling"] = "설명 문구만 바꾼 경우"
        contract["image_ocr"]["value_basis"] = "changed"
        self.assertEqual(office_sha(contract), OFFICE_CONFIG_SHA256)
        self.assertEqual(image_ocr_config_sha256(contract), IMAGE_OCR_CONFIG_SHA256)

    def test_a_new_snapshot_changes_keys_on_purpose(self):
        contract = copy.deepcopy(parsing_contract())
        snapshot = copy.deepcopy(contract["config_identity_snapshots"]["office_v1"])
        snapshot["office_parser_version"] = 2
        contract["config_identity_snapshots"]["office_v2"] = snapshot
        contract["office"]["identity_snapshot"] = "office_v2"
        self.assertNotEqual(office_sha(contract), OFFICE_CONFIG_SHA256)

    def test_live_settings_match_their_snapshot(self):
        # BOUNDARY: 코드는 살아 있는 구역의 설정 값(타일 크기 등)을 읽는다. 설정을 바꾸고 snapshot을 새로 만들지 않으면
        # 결과가 바뀌는데 key는 그대로인 상태가 되므로, 문자열이 아닌 설정 값은 snapshot과 같아야 한다.
        contract = parsing_contract()
        for section in ("office", "image_ocr"):
            live = contract[section]
            snapshot = contract["config_identity_snapshots"][live["identity_snapshot"]]
            settings = {key: value for key, value in snapshot.items() if not isinstance(value, str)}
            self.assertTrue(settings, section)
            for key, value in settings.items():
                self.assertEqual(live.get(key), value, f"{section}.{key}")


if __name__ == "__main__":
    unittest.main()
