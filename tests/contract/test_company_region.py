import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data-pipeline/src"))

from biz_aid_pipeline.candidates.region import excluded_jurisdictions, region_contract, standard_regions

MIGRATION = ROOT / "migrations/V11__company_region_standard.sql"


class CompanyRegionContractTests(unittest.TestCase):
    def test_contract_is_the_single_mapping_source(self):
        contract = region_contract()
        regions = contract["regions"]
        # 2026-10-03 결정 가안: 데이터 기준 광역 16개(광주·전남은 전남광주통합특별시 하나).
        self.assertEqual(len(regions), 16)
        self.assertIn("전남광주통합특별시", regions)
        self.assertNotIn("광주광역시", regions)
        self.assertEqual(set(contract["jurisdiction_regions"].values()), set(regions))
        self.assertEqual(set(contract["aliases"]), set(regions))
        # 중앙부처 목록과 지자체 매핑은 겹치지 않는다.
        self.assertFalse(set(contract["national_jurisdictions"]) & set(contract["jurisdiction_regions"]))
        # 광주·전남 옛 이름은 통합 표준명으로 바뀐다(사용자 결정 ①).
        for alias in ("광주", "광주광역시", "전남", "전라남도"):
            self.assertIn(alias, contract["aliases"]["전남광주통합특별시"])
        self.assertEqual(standard_regions(), tuple(regions))

    def test_excluded_jurisdictions_are_other_metropolitan_governments_only(self):
        excluded = excluded_jurisdictions("경기도")
        self.assertEqual(len(excluded), 15)
        self.assertNotIn("경기도", excluded)
        self.assertNotIn("중소벤처기업부", excluded)
        # 표준명이 아니면 지역 조건을 적용하지 않는다(None).
        self.assertIsNone(excluded_jurisdictions("경기도 광명시"))
        self.assertIsNone(excluded_jurisdictions("광주광역시"))

    def test_approved_migration_converts_with_the_contract_aliases(self):
        contract = region_contract()
        sql = MIGRATION.read_text(encoding="utf-8")
        # 계약의 모든 별칭이 변환문에 있고, 어떤 별칭에도 맞지 않는 값은 NULL이 된다.
        for region, aliases in contract["aliases"].items():
            for alias in aliases:
                self.assertIn(f"'{alias}%' THEN '{region}'", sql, alias)
        self.assertIn("ELSE NULL", sql)
        # 긴 별칭이 먼저 검사된다(예: 전남광주통합특별시가 전남보다 먼저).
        order = re.findall(r"LIKE '([^%']+)%'", sql)
        self.assertEqual(order, sorted(order, key=len, reverse=True))
        self.assertIn("COMMENT", sql)
        # BOUNDARY: 사용자 적용 승인 뒤 공통 Flyway 계보로 이동했으며 pending 복사본을 남기지 않는다.
        self.assertFalse((ROOT / "data-pipeline/pending-migrations" / MIGRATION.name).exists())
        self.assertIn("적용 승인", sql)


if __name__ == "__main__":
    unittest.main()
