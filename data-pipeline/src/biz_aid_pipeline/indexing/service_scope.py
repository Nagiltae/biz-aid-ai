"""V2 서비스 검색 범위 선정. MySQL·S3는 과거 공고까지 전부 보관하고, Qdrant(V2)에는 종료가 확실하지 않은 공고의 문서만 적재한다.

상태 판정은 기존 규칙과 같다(candidates/service.py의 신청기간 조건, Spring RecruitmentStatus):
- CLOSED: 파생 종료일이 있고 기준일보다 이전 → 종료가 확실하므로 제외
- UPCOMING: 시작일이 기준일보다 이후 → 아직 종료 전이므로 포함
- OPEN: 날짜 범위가 기준일을 포함 → 포함
- UNKNOWN: 시작·종료일이 모두 없음("예산 소진시까지" 등) → 날짜만으로 종료를 확정할 수 없으므로 포함
새 DB column 없이 기존 application_start_date·application_end_date에서 파생한다.
"""
import argparse
import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import MetaData, Table, and_, case, create_engine, func, select
from sqlalchemy.engine import URL

from biz_aid_pipeline.config.settings import ROOT, DbConfig, PipelineError

OUTPUT = Path("data/parsed/v2-service-scope")


def state_expression(programs, as_of):
    start, end = programs.c.application_start_date, programs.c.application_end_date
    return case((and_(start.is_(None), end.is_(None)), "UNKNOWN"),
                (and_(end.is_not(None), end < as_of), "CLOSED"),
                (and_(start.is_not(None), start > as_of), "UPCOMING"), else_="OPEN")


def select_scope(engine, as_of, enabled_formats):
    """활성 공고의 상태별 수와, CLOSED가 아닌 공고에 연결된 검증 원본 문서(enabled format) 목록을 돌려준다."""
    metadata = MetaData()
    programs = Table("support_programs", metadata, autoload_with=engine)
    sources = Table("document_sources", metadata, autoload_with=engine)
    state = state_expression(programs, as_of).label("state")
    active = and_(programs.c.source_active.is_(True), programs.c.source_deleted.is_(False))
    with engine.connect() as connection:
        counts = dict(connection.execute(select(state, func.count()).where(active).group_by(state)).all())
        service_ids = connection.execute(select(programs.c.pblanc_id).where(active, state != "CLOSED")
                                         .order_by(programs.c.pblanc_id)).scalars().all()
        # 검증된 S3 원본만 대상이다(parsing corpus 선택 조건과 같음). 같은 파일이 여러 공고에 붙으면 SHA 하나로 처리한다.
        rows = connection.execute(select(sources.c.content_sha256, sources.c.detected_format, sources.c.pblanc_id).where(
            sources.c.pblanc_id.in_(service_ids), sources.c.download_status == "ACQUIRED",
            sources.c.s3_object_key.is_not(None), sources.c.s3_verified_at.is_not(None),
            sources.c.detected_format.in_(list(enabled_formats)))).all()
    documents = {}
    for sha, detected, _ in rows:
        documents.setdefault(sha, detected)
    with_documents = {pblanc for _, _, pblanc in rows}
    by_format = {}
    for detected in documents.values():
        by_format[detected] = by_format.get(detected, 0) + 1
    return {"as_of": str(as_of), "program_states": {key: counts.get(key, 0) for key in ("OPEN", "UPCOMING", "UNKNOWN", "CLOSED")},
            "service_programs": len(service_ids), "service_programs_with_documents": len(with_documents),
            "service_documents": len(documents), "service_documents_by_format": dict(sorted(by_format.items())),
            "excluded_closed_programs": counts.get("CLOSED", 0)}, sorted(service_ids), sorted(documents)


def main(argv=None):
    parser = argparse.ArgumentParser(description="dev-only V2 service scope (non-closed programs → documents to index)")
    parser.add_argument("--profile", choices=["dev"], required=True)
    parser.add_argument("--as-of", help="기준일 YYYY-MM-DD(기본: Asia/Seoul 오늘)")
    args = parser.parse_args(argv)
    from biz_aid_pipeline.parsing.models import parsing_contract
    as_of = date.fromisoformat(args.as_of) if args.as_of else datetime.now(ZoneInfo("Asia/Seoul")).date()
    config = DbConfig.load(ROOT, args.profile)
    if config.profile != "dev" or config.database not in ("biz_aid_dev", "biz_aid_test"):
        raise PipelineError("dev_database_boundary")
    engine = create_engine(URL.create("mysql+pymysql", username=config.user, password=config.password, host=config.host,
                                      port=config.port, database=config.database, query={"charset": "utf8mb4"}),
                           hide_parameters=True)
    try:
        enabled = [fmt for fmt, route in parsing_contract()["routes"].items() if route["enabled"]]
        summary, program_ids, documents = select_scope(engine, as_of, enabled)
    finally:
        engine.dispose()
    directory = ROOT / OUTPUT / str(as_of)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "programs.txt").write_text("".join(item + "\n" for item in program_ids), encoding="utf-8")
    (directory / "sources.txt").write_text("".join(item + "\n" for item in documents), encoding="utf-8")
    (directory / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"sources: {directory / 'sources.txt'}")
    return 0
