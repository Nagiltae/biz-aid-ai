"""자연어 질문 → LLM 구조화 추출 → 허용 값 검증 → ProgramCandidateFilter.

LLM은 필터 입력 후보만 제안한다. SQL·활성 여부·후보 선택·날짜는 application이 정한다.
허용 값은 MySQL support_programs의 실제 값(활성 공고 기준)이며, 목록 밖 값은 적용하지 않고 unapplied로 드러낸다.
"""
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select

from biz_aid_pipeline.candidates.service import ProgramCandidateFilter
from biz_aid_pipeline.config.settings import PipelineError
from biz_aid_pipeline.rag.llm import LlmRequest

# 공고 날짜는 한국 기관 기준이므로 "지금"은 한국 시간의 날짜로 해석한다.
SERVICE_TIMEZONE = "Asia/Seoul"

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"categories": {"type": "array", "items": {"type": "string"}},
                   "targets": {"type": "array", "items": {"type": "string"}},
                   "currently_open_requested": {"type": "boolean"},
                   "unapplied_constraints": {"type": "array", "items": {"type": "string"}}},
    "required": ["categories", "targets", "currently_open_requested", "unapplied_constraints"],
}

SYSTEM_TEMPLATE = """너는 지원사업 검색 질문에서 정형 검색 조건만 뽑는 도구다. 답변이나 설명을 하지 않는다.
허용 값 목록에 있는 값만 그대로 복사해 쓴다. 목록에 없는 말로 바꾸거나 새 값을 만들지 않는다.
- categories(지원분야): {categories}
- targets(지원대상 구분): {targets}
규칙:
1. 질문이 명시적으로 말한 조건만 넣는다. 추측하지 않는다.
2. "지금 신청 가능", "현재 모집 중", "마감 안 된" 같은 표현이 있으면 currently_open_requested를 true로 한다. 날짜는 절대 만들지 않는다.
3. 지역(서울·부산·경기도 소재 등), 소관기관, 업력, 매출, 금액, 인원처럼 위 목록으로 표현할 수 없는 조건은 unapplied_constraints에 짧은 한국어 구로 넣는다(예: "서울 지역").
4. 특정 사업명·세부 내용 질문은 조건이 아니다. 조건이 없으면 빈 목록과 false를 낸다.
결과는 지정된 JSON 형식으로만 출력한다."""


@dataclass
class NaturalFilterResult:
    candidate_filter: ProgramCandidateFilter
    raw: dict
    applied: dict
    unapplied_constraints: list
    as_of: str | None

    def to_dict(self):
        value = asdict(self)
        value["candidate_filter"] = {key: (str(item) if key == "not_closed_on" and item else item)
                                     for key, item in value["candidate_filter"].items()}
        return value


def service_today():
    return datetime.now(ZoneInfo(SERVICE_TIMEZONE)).date()


def filter_domain(repository):
    """허용 값: 활성 공고에 실제로 있는 category·target. 새 정규화 표를 만들지 않고 DB 값을 그대로 쓴다."""
    table = repository.programs.c
    with repository.engine.connect() as connection:
        active = (table.source_active.is_(True), table.source_deleted.is_(False))
        values = {name: tuple(sorted(connection.execute(select(column).where(*active, column.is_not(None)).distinct()).scalars().all()))
                  for name, column in (("categories", table.category), ("targets", table.target))}
    return values


class NaturalLanguageFilterService:
    def __init__(self, provider, domain):
        self.provider, self.domain = provider, domain

    def extract(self, query, as_of=None):
        system = SYSTEM_TEMPLATE.format(categories=", ".join(self.domain["categories"]), targets=", ".join(self.domain["targets"]))
        response = self.provider.generate(LlmRequest(system, f"질문: {query}", OUTPUT_SCHEMA))
        # BOUNDARY: 추출 실패를 "조건 없음"으로 바꾸면 전체 공고를 검색하게 된다. 조용한 fallback 없이 실패시킨다.
        try:
            raw = json.loads(response.text)
        except ValueError:
            raise PipelineError("filter_extraction_output_not_json") from None
        if (not isinstance(raw, dict) or not isinstance(raw.get("currently_open_requested"), bool)
                or any(not isinstance(raw.get(key), list) or not all(isinstance(item, str) for item in raw[key])
                       for key in ("categories", "targets", "unapplied_constraints"))):
            raise PipelineError("filter_extraction_schema_mismatch")
        applied, unapplied = {}, [item.strip() for item in raw["unapplied_constraints"] if item.strip()]
        for key in ("categories", "targets"):
            allowed = set(self.domain[key])
            values = list(dict.fromkeys(item.strip() for item in raw[key] if item.strip()))
            # WHY: 목록 밖 값("finance", "금융지원")을 SQL에 그대로 넣으면 0건이 되거나 다른 뜻이 된다. 적용하지 않고 드러낸다.
            applied[key] = tuple(value for value in values if value in allowed)
            unapplied += [f"{key}:{value}(허용 값 아님)" for value in values if value not in allowed]
        day = (as_of or service_today()) if raw["currently_open_requested"] else None
        candidate_filter = ProgramCandidateFilter(categories=applied["categories"], targets=applied["targets"], not_closed_on=day)
        return NaturalFilterResult(candidate_filter, raw, {key: list(value) for key, value in applied.items()},
                                   list(dict.fromkeys(unapplied)), str(day) if day else None)
