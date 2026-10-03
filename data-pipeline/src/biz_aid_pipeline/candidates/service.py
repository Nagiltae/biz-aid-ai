"""MySQL 정형 조건으로 검색 대상 공고(pblanc_id)를 정한다. RAG·Retriever보다 먼저 적용하는 authoritative 후보 집합이다.

실제 schema에서 값이 고정된 정형 column만 hard filter로 쓴다. 자유 텍스트(지역 hashtag·신청기간 원문)는 해석하지 않는다.
"""
from dataclasses import dataclass
from datetime import date

from sqlalchemy import MetaData, Table, and_, create_engine, func, not_, or_, select
from sqlalchemy.engine import URL

from biz_aid_pipeline.config.settings import PipelineError


@dataclass(frozen=True)
class ProgramCandidateFilter:
    """값이 여러 개면 OR, 필드끼리는 AND. 빈 필드는 조건 없음이다."""

    categories: tuple = ()        # support_programs.category (지원분야 대분류, 예: 금융·기술)
    targets: tuple = ()           # support_programs.target (지원대상 구분, 예: 소상공인)
    jurisdictions: tuple = ()     # support_programs.jurisdiction_name (소관기관, 예: 경기도·중소벤처기업부)
    # 이 소관기관 공고는 뺀다(기업 지역과 다른 광역 지자체, company-region 계약). 빈 값은 조건 없음이다.
    exclude_jurisdictions: tuple = ()
    not_closed_on: date | None = None  # 파생 신청기간이 이 날짜를 포함하지 않는 공고만 제외
    # V2 서비스 검색 범위: 이 날짜 전에 종료가 확실한(CLOSED) 공고만 제외한다. 시작 전(UPCOMING)·날짜 없음(UNKNOWN)은 남긴다.
    exclude_closed_on: date | None = None


@dataclass(frozen=True)
class CandidateSet:
    pblanc_ids: tuple
    period_unknown: int  # not_closed_on을 줬을 때 파생 신청기간이 없어 제외하지 않고 남긴 공고 수


class ProgramCandidateRepository:
    """support_programs read-only 조회. INSERT·UPDATE·DDL을 하지 않는다."""

    def __init__(self, engine):
        self.engine = engine
        try:
            self.programs = Table("support_programs", MetaData(), autoload_with=engine)
        except Exception:
            raise PipelineError("support_program_schema_unavailable_run_flyway") from None

    @classmethod
    def from_config(cls, config):
        if (config.profile != "dev" or config.database not in ("biz_aid_dev", "biz_aid_test")
                or config.host not in ("localhost", "127.0.0.1", "mysql") or config.port != 3306):
            raise PipelineError("dev_database_boundary")
        return cls(create_engine(URL.create("mysql+pymysql", username=config.user, password=config.password,
            host=config.host, port=config.port, database=config.database, query={"charset": "utf8mb4"}),
            hide_parameters=True, echo=False, pool_pre_ping=True,
            connect_args={"connect_timeout": 5, "read_timeout": 30, "write_timeout": 30}))

    def find(self, candidate_filter):
        table = self.programs.c
        # BOUNDARY: 현재 서비스 대상은 API universe에 살아 있는 공고뿐이다(V1 lifecycle: active=1이면 deleted=0).
        conditions = [table.source_active.is_(True), table.source_deleted.is_(False)]
        for column, values in ((table.category, candidate_filter.categories), (table.target, candidate_filter.targets),
                               (table.jurisdiction_name, candidate_filter.jurisdictions)):
            if values:
                conditions.append(column.in_(values))
        if candidate_filter.exclude_jurisdictions:
            conditions.append(table.jurisdiction_name.not_in(candidate_filter.exclude_jurisdictions))
        if candidate_filter.exclude_closed_on is not None:
            closed_on = candidate_filter.exclude_closed_on
            conditions.append(not_(and_(table.application_end_date.is_not(None), table.application_end_date < closed_on)))
        unknown = None
        if candidate_filter.not_closed_on is not None:
            day = candidate_filter.not_closed_on
            # WHY: 신청기간 파생 날짜는 원문이 유효한 날짜 범위일 때만 있다. "예산 소진시까지" 같은 원문은 마감을 판정할 수 없어 제외하지 않는다.
            conditions.append(not_(or_(and_(table.application_end_date.is_not(None), table.application_end_date < day),
                                       and_(table.application_start_date.is_not(None), table.application_start_date > day))))
            unknown = and_(table.application_start_date.is_(None), table.application_end_date.is_(None))
        with self.engine.connect() as connection:
            ids = connection.execute(select(table.pblanc_id).where(*conditions).distinct().order_by(table.pblanc_id)).scalars().all()
            undated = connection.execute(select(func.count()).select_from(self.programs).where(*conditions, unknown)).scalar_one() if unknown is not None else 0
        return CandidateSet(tuple(ids), undated)

    def program_metadata(self, pblanc_ids):
        """목록 응답용 공고 정형 정보. MySQL 값을 그대로 돌려주며 원문에서 새 정보를 추론하지 않는다."""
        table = self.programs.c
        columns = (table.pblanc_id, table.name, table.category, table.target, table.jurisdiction_name, table.executing_org_name,
                   table.application_start_date, table.application_end_date, table.application_period_raw, table.announcement_url)
        with self.engine.connect() as connection:
            rows = connection.execute(select(*columns).where(table.pblanc_id.in_(list(pblanc_ids)), table.source_active.is_(True),
                                                             table.source_deleted.is_(False))).mappings().all()
        return {row["pblanc_id"]: dict(row) for row in rows}

    def close(self):
        self.engine.dispose()


class ProgramCandidateService:
    def __init__(self, repository):
        self.repository = repository

    def find_candidates(self, candidate_filter):
        return self.repository.find(candidate_filter)
