"""자연어 질문 → LLM 구조화 추출 → 허용 값 검증 → ProgramCandidateFilter.

LLM은 필터 입력 후보만 제안한다. SQL·활성 여부·후보 선택·날짜는 application이 정한다.
허용 값은 MySQL support_programs의 실제 값(활성 공고 기준)이며, 목록 밖 값은 적용하지 않고 unapplied로 드러낸다.
"""
import copy
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

REQUEST_MODES = ("SEARCH_LIST", "DOCUMENT_QA")
# WHY: "지금 신청 가능" 필터는 후보를 실제로 줄이는 hard filter다. 질문에 이 계열 표현이 없으면 모델이 true를 내도 적용하지 않는다(IMP-012).
OPEN_PHRASES = ("지금", "현재", "신청가능", "신청할수있", "모집중", "접수중", "마감안", "마감되지않", "마감전", "아직신청", "오늘신청")

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"request_mode": {"type": "string", "enum": list(REQUEST_MODES)},
                   "categories": {"type": "array", "items": {"type": "string"}},
                   "targets": {"type": "array", "items": {"type": "string"}},
                   "currently_open_requested": {"type": "boolean"},
                   "unapplied_constraints": {"type": "array", "items": {"type": "string"}}},
    "required": ["request_mode", "categories", "targets", "currently_open_requested", "unapplied_constraints"],
}

def output_schema(domain):
    """요청마다 허용값을 넣은 출력 schema. 분야·대상은 DB에 실제로 있는 값 중에서만 고르게 생성 단계에서 제한한다(enum).

    생성 단계 제한은 형식 안정화용이다. 질문 근거 검사(grounded)·허용값 재검증은 extract()에서 그대로 한다.
    """
    schema = copy.deepcopy(OUTPUT_SCHEMA)
    for key in ("categories", "targets"):
        if domain.get(key):
            schema["properties"][key]["items"]["enum"] = list(domain[key])
    return schema


SYSTEM_TEMPLATE = """너는 지원사업 검색 질문에서 정형 검색 조건만 뽑는 도구다. 답변이나 설명을 하지 않는다.
허용 값 목록에 있는 값만 그대로 복사해 쓴다. 목록에 없는 말로 바꾸거나 새 값을 만들지 않는다.
- categories(지원분야): {categories}
- targets(지원대상 구분): {targets}
규칙:
1. 질문이 명시적으로 말한 조건만 넣는다. 추측하지 않는다.
2. "지금 신청 가능", "현재 모집 중", "마감 안 된" 같은 표현이 있으면 currently_open_requested를 true로 한다. 날짜는 절대 만들지 않는다.
3. 지역, 소관기관, 업력, 매출, 금액, 인원처럼 위 목록으로 표현할 수 없는 조건이 질문에 실제로 있으면 질문 속 표현 그대로 unapplied_constraints에 넣는다. 질문에 없는 조건은 넣지 않는다.
4. 특정 사업명·세부 내용 질문은 조건이 아니다. 조건이 없으면 빈 목록과 false를 낸다.
5. request_mode: 조건에 맞는 지원사업을 찾거나 목록을 원하면 SEARCH_LIST, 특정 공고·사업의 내용(요건·금액·기간·서류 등)을 물으면 DOCUMENT_QA.
결과는 지정된 JSON 형식으로만 출력한다."""


@dataclass
class NaturalFilterResult:
    request_mode: str
    candidate_filter: ProgramCandidateFilter
    raw: dict
    applied: dict
    unapplied_constraints: list
    discarded: list  # 질문에 근거가 없어 버린 모델 제안 [{field, value, reason}]
    as_of: str | None

    def to_dict(self):
        value = asdict(self)
        value["candidate_filter"] = {key: (str(item) if key == "not_closed_on" and item else item)
                                     for key, item in value["candidate_filter"].items()}
        return value


def compact(text):
    return "".join(text.split())


def grounded(value, query):
    """질문 원문에 값의 표현이 그대로 있는가(공백 무시). 동의어·추론 없이 보수적으로 판정한다."""
    return bool(compact(value)) and compact(value) in compact(query)


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

    def extract(self, query, as_of=None, request_mode=None):
        system = SYSTEM_TEMPLATE.format(categories=", ".join(self.domain["categories"]), targets=", ".join(self.domain["targets"]))
        schema = output_schema(self.domain)
        if request_mode is not None:
            if request_mode not in REQUEST_MODES:
                raise PipelineError("filter_request_mode_invalid")
            # BOUNDARY: 명확한 의도는 규칙이 먼저 결정한다. LLM은 나머지 정형 조건만 추출한다.
            schema["properties"]["request_mode"]["enum"] = [request_mode]
        response = self.provider.generate(LlmRequest(system, f"질문: {query}", schema))
        # BOUNDARY: 추출 실패를 "조건 없음"으로 바꾸면 전체 공고를 검색하게 된다. 조용한 fallback 없이 실패시킨다.
        try:
            raw = json.loads(response.text)
        except ValueError:
            raise PipelineError("filter_extraction_output_not_json") from None
        if (not isinstance(raw, dict) or raw.get("request_mode") not in REQUEST_MODES
                or not isinstance(raw.get("currently_open_requested"), bool)
                or any(not isinstance(raw.get(key), list) or not all(isinstance(item, str) for item in raw[key])
                       for key in ("categories", "targets", "unapplied_constraints"))):
            raise PipelineError("filter_extraction_schema_mismatch")
        applied, unapplied, discarded = {}, [], []
        for item in dict.fromkeys(item.strip() for item in raw["unapplied_constraints"] if item.strip()):
            # 질문에 없는 자유 문구는 적용 안 된 조건으로 보고하지 않고 진단용으로만 남긴다.
            (unapplied if grounded(item, query) else discarded).append(
                item if grounded(item, query) else {"field": "unapplied_constraints", "value": item, "reason": "not_in_query"})
        for key in ("categories", "targets"):
            allowed, kept = set(self.domain[key]), []
            for value in dict.fromkeys(item.strip() for item in raw[key] if item.strip()):
                # BOUNDARY: hard filter는 허용 값이면서 질문에 그 표현이 있을 때만 적용한다. 모델이 만든 값이 후보를 줄이지 못하게 한다.
                if not grounded(value, query):
                    discarded.append({"field": key, "value": value, "reason": "not_in_query"})
                elif value in allowed:
                    kept.append(value)
                else:
                    unapplied.append(f"{key}:{value}(허용 값 아님)")
            applied[key] = tuple(kept)
        open_requested = raw["currently_open_requested"]
        if open_requested and not any(phrase in compact(query) for phrase in OPEN_PHRASES):
            discarded.append({"field": "currently_open_requested", "value": True, "reason": "no_open_phrase_in_query"})
            open_requested = False
        day = (as_of or service_today()) if open_requested else None
        candidate_filter = ProgramCandidateFilter(categories=applied["categories"], targets=applied["targets"], not_closed_on=day)
        return NaturalFilterResult(request_mode or raw["request_mode"], candidate_filter, raw, {key: list(value) for key, value in applied.items()},
                                   list(dict.fromkeys(unapplied)), discarded, str(day) if day else None)
