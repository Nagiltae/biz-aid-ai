import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data-pipeline/src"))

from sqlalchemy import Boolean, Column, Date, MetaData, String, Table, create_engine, insert

from biz_aid_pipeline.candidates.service import ProgramCandidateFilter, ProgramCandidateRepository, ProgramCandidateService


def engine_with(rows):
    """V1 support_programs 중 후보 조회가 읽는 column만 가진 in-memory 표. SQL 의미는 dialect와 무관한 Core 조건이다."""
    engine = create_engine("sqlite://")
    metadata = MetaData()
    table = Table("support_programs", metadata, Column("pblanc_id", String, unique=True), Column("category", String),
                  Column("target", String), Column("jurisdiction_name", String), Column("application_start_date", Date),
                  Column("application_end_date", Date), Column("source_active", Boolean), Column("source_deleted", Boolean),
                  Column("name", String), Column("executing_org_name", String), Column("application_period_raw", String),
                  Column("announcement_url", String))
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(insert(table), rows)
    return engine


def row(pblanc_id, category="금융", target="소상공인", jurisdiction="경기도", start=None, end=None, active=True):
    return {"pblanc_id": pblanc_id, "category": category, "target": target, "jurisdiction_name": jurisdiction,
            "application_start_date": start, "application_end_date": end, "source_active": active, "source_deleted": not active,
            "name": f"공고 {pblanc_id}", "executing_org_name": None, "application_period_raw": None, "announcement_url": None}


class ProgramCandidateContractTests(unittest.TestCase):
    def test_candidates_follow_structured_filters_lifecycle_and_period_without_guessing(self):
        rows = [row("P3"), row("P1", end=date(2026, 12, 31), start=date(2026, 1, 1)), row("P2", category="기술"),
                row("P4", active=False), row("P5", end=date(2026, 3, 31), start=date(2026, 1, 1)),
                row("P6", start=date(2026, 11, 1), end=date(2026, 12, 31)), row("P7", target="중소기업", jurisdiction="중소벤처기업부")]
        service = ProgramCandidateService(ProgramCandidateRepository(engine_with(rows)))
        # BOUNDARY: 비활성·삭제 공고(P4)는 어떤 조건에서도 후보가 아니다. 결과는 중복 없이 pblanc_id 오름차순이다.
        everything = service.find_candidates(ProgramCandidateFilter())
        self.assertEqual(everything.pblanc_ids, ("P1", "P2", "P3", "P5", "P6", "P7"))
        self.assertEqual(service.find_candidates(ProgramCandidateFilter(categories=("금융",), targets=("소상공인",))).pblanc_ids,
                         ("P1", "P3", "P5", "P6"))
        self.assertEqual(service.find_candidates(ProgramCandidateFilter(jurisdictions=("중소벤처기업부", "없는기관"))).pblanc_ids, ("P7",))
        # 마감(P5)·시작 전(P6)만 제외하고, 파생 신청기간이 없는 공고는 마감을 판정할 수 없어 남기고 수를 알린다.
        open_now = service.find_candidates(ProgramCandidateFilter(not_closed_on=date(2026, 9, 30)))
        self.assertEqual(open_now.pblanc_ids, ("P1", "P2", "P3", "P7"))
        self.assertEqual(open_now.period_unknown, 3)
        self.assertEqual(service.find_candidates(ProgramCandidateFilter(categories=("없는분야",))).pblanc_ids, ())


if __name__ == "__main__":
    unittest.main()
