"""V2 기업정보 기반 개인화 검색: 기업정보 조건(코드) + 질문 조건(Natural Filter) → MySQL 후보 → 공고 단위 검색 Top 3.

BOUNDARY: 기업정보는 Spring이 소유하고 요청 때 snapshot으로 받는다. 여기서 users·companies 테이블을 읽지 않는다.
저장된 기업정보의 확실한 사실만 일반 코드로 검색조건이 된다. LLM은 기업정보를 해석하지 않는다(질문 조건 추출만 한다).
의미가 확실하지 않은 값(업력, 휴업 등)은 Hard Filter로 추측하지 않고 unapplied로 드러낸다.
지역은 기업 지역과 전국 공고를 남긴다. 제목의 복수 지역 표시·중앙부처 제목 지역은 company-region 계약을 따른다.
순위(IMP-019 A안, 2026-10-06): 업종·업력·직원 수·매출 구간·사업자 형태·수출/벤처/연구소로 코드가 짧은 기업정보 문장을 만들고,
같은 후보 안에서 그 문장으로 한 번 더 공고 검색해 질문 검색 순위와 가중 RRF로 합친다. 질문 비중이 항상 더 크다. LLM은 쓰지 않는다.
"""
from dataclasses import dataclass, fields
from datetime import date

from biz_aid_pipeline.candidates.region import excluded_jurisdictions, region_contract
from biz_aid_pipeline.rag.service import rag_contract
from biz_aid_pipeline.candidates.service import ProgramCandidateFilter
from biz_aid_pipeline.config.settings import PipelineError

TOP_K = 3

# 사용자 승인 매핑(2026-10-01): 기업규모 → 신청 가능한 지원대상(target).
# 소상공인은 법적으로 중소기업에 포함되므로 '중소기업' 공고도 남긴다. 사회적기업·여성기업 등 인증이 필요한 대상은
# 기업정보에 인증 여부가 없어 기업규모 필터를 적용할 때 후보에서 뺀다. 표에 없는 규모는 필터를 적용하지 않는다.
SIZE_TARGETS = {"소상공인": ("소상공인", "중소기업"), "중소기업": ("중소기업",)}
BUSINESS_STATUSES = ("영업중", "휴업", "폐업")


@dataclass(frozen=True)
class CompanySearchProfile:
    """개인화 검색에 필요한 기업정보만 담은 snapshot. 모두 선택값이다.

    앞 4개는 후보 조건(필터)에, 나머지는 순위용 기업정보 문장에만 쓴다(IMP-019). 신용·체납 같은 민감 사실은 받지 않는다.
    """

    company_size: str | None = None
    business_status: str | None = None
    region: str | None = None
    business_start_date: date | None = None
    industry: str | None = None
    business_entity_type: str | None = None
    employee_count: int | None = None
    annual_revenue_krw: int | None = None
    exporter: bool | None = None
    venture_certified: bool | None = None
    research_institute: bool | None = None

    @classmethod
    def from_dict(cls, value):
        known = {item.name for item in fields(cls)}
        unknown = sorted(set(value) - known)
        if unknown:
            raise PipelineError("company_search_profile_unknown_field:" + ",".join(unknown))
        data = {key: (item.strip() if isinstance(item, str) else item) or None for key, item in value.items()}
        if data.get("business_status") is not None and data["business_status"] not in BUSINESS_STATUSES:
            raise PipelineError("company_search_profile_invalid:business_status")
        try:
            if data.get("business_start_date"):
                data["business_start_date"] = date.fromisoformat(str(data["business_start_date"]))
        except ValueError:
            raise PipelineError("company_search_profile_invalid:business_start_date") from None
        for name in ("employee_count", "annual_revenue_krw"):
            if data.get(name) is not None and (isinstance(data[name], bool) or not isinstance(data[name], int) or data[name] < 0):
                raise PipelineError("company_search_profile_invalid:" + name)
        for name in ("exporter", "venture_certified", "research_institute"):
            if data.get(name) is not None and not isinstance(data[name], bool):
                raise PipelineError("company_search_profile_invalid:" + name)
        return cls(**data)


def _bucket(value, bounds):
    """값을 구간 이름으로 바꾼다. bounds는 (상한 미만, 이름) 순서이고 마지막 이름은 그 이상이다."""
    for upper, name in bounds[:-1]:
        if value < upper:
            return name
    return bounds[-1][1]


def company_query(profile, as_of):
    """기업정보 → 순위용 짧은 검색 문장과 사용한 항목 이름. 해당 항목이 하나도 없으면 (None, []).

    BOUNDARY: 원래 값 대신 구간·분류 단어만 쓴다(직원 수·매출·개업일 원값을 검색 문장에 넣지 않음).
    RISK: 이 문장은 기업정보에서 나온 값이라 로그·추적·응답에 남기지 않는다. 호출자는 항목 이름만 기록한다.
    """
    parts, used = [], []
    if profile.industry:
        parts.append(profile.industry)
        used.append("industry")
    if profile.business_entity_type:
        parts.append(profile.business_entity_type)
        used.append("business_entity_type")
    if profile.business_start_date is not None and profile.business_start_date <= as_of:
        months = (as_of.year - profile.business_start_date.year) * 12 + as_of.month - profile.business_start_date.month
        parts.append(_bucket(months, ((12, "창업 1년 미만 초기 창업기업"), (36, "창업 3년 이내 창업기업"),
                                      (84, "업력 7년 이내 기업"), (None, "업력 7년 이상 기업"))))
        used.append("business_start_date")
    if profile.employee_count is not None:
        parts.append(_bucket(profile.employee_count, ((5, "상시근로자 5인 미만"), (10, "상시근로자 10인 미만"),
                                                      (50, "상시근로자 50인 미만"), (300, "상시근로자 300인 미만"),
                                                      (None, "상시근로자 300인 이상"))))
        used.append("employee_count")
    if profile.annual_revenue_krw is not None:
        parts.append(_bucket(profile.annual_revenue_krw, ((100_000_000, "연매출 1억 미만"), (1_000_000_000, "연매출 10억 미만"),
                                                          (10_000_000_000, "연매출 100억 미만"), (None, "연매출 100억 이상"))))
        used.append("annual_revenue_krw")
    # 아니오(False)는 검색어로 넣지 않는다("수출 안 함"이 수출 공고와 가까워지는 역효과를 막음).
    for name, word in (("exporter", "수출기업"), ("venture_certified", "벤처기업"), ("research_institute", "기업부설연구소 보유 기술개발")):
        if getattr(profile, name) is True:
            parts.append(word)
            used.append(name)
    return (" ".join(parts), used) if parts else (None, [])


def generic_question(extraction):
    """질문에서 분야·지원대상·소관기관 조건이 하나도 추출되지 않았으면 일반 질문으로 본다(예: "우리 회사에 맞는 지원사업 추천해줘")."""
    found = extraction.candidate_filter
    return not (found.categories or found.targets or found.jurisdictions)


def blend_rankings(question_items, company_items, company_weight, rrf_k, limit):
    """질문 검색 순위(가중치 1)와 기업정보 검색 순위(company_weight<1)를 가중 RRF로 합친다.

    WHY: 두 검색은 같은 후보·같은 공고 단위라 순위만 합치면 척도 차이가 없다. 질문 가중치를 더 크게 둬 질문 의도를 우선한다.
    질문 검색에 없던 공고는 기업정보 검색 순위만으로 들어올 수 있지만 질문 1위보다 앞서려면 두 검색 모두에서 높아야 한다.
    """
    question = {item["pblanc_id"]: item for item in question_items}
    company = {item["pblanc_id"]: item for item in company_items}
    scores = {}
    for pblanc_id in set(question) | set(company):
        q_rank = question[pblanc_id]["rank"] if pblanc_id in question else None
        c_rank = company[pblanc_id]["rank"] if pblanc_id in company else None
        score = (1.0 / (rrf_k + q_rank) if q_rank else 0.0) + (company_weight / (rrf_k + c_rank) if c_rank else 0.0)
        scores[pblanc_id] = (score, q_rank, c_rank)
    # 동점은 질문 순위, 그다음 공고 ID로 정해 실행마다 같은 순서를 낸다.
    ordered = sorted(scores, key=lambda key: (-scores[key][0], scores[key][1] or 10**6, key))[:limit]
    blended = []
    for rank, pblanc_id in enumerate(ordered, 1):
        score, q_rank, c_rank = scores[pblanc_id]
        base = question.get(pblanc_id) or company[pblanc_id]
        blended.append(dict(base, rank=rank, rrf_score=question[pblanc_id].get("rrf_score") if q_rank else None,
                            question_rank=q_rank, company_rank=c_rank, company_weight=company_weight, blended_score=score))
    return blended


@dataclass(frozen=True)
class CompanyConditions:
    targets: tuple | None  # None = 기업정보로 정한 지원대상 조건 없음
    closed_company: bool
    unapplied: list
    region: str | None = None               # 적용한 기업 지역(표준명). None = 지역 조건 없음
    excluded_jurisdictions: tuple = ()      # 기업 지역과 다른 광역 소관기관(후보에서 제외)


def company_conditions(profile):
    """기업정보 → 검색조건. 확실한 매핑만 적용하고 나머지는 이유와 함께 unapplied로 남긴다."""
    unapplied = []
    targets = SIZE_TARGETS.get(profile.company_size) if profile.company_size else None
    if profile.company_size and targets is None:
        unapplied.append({"source": "company", "field": "company_size", "value": profile.company_size,
                          "reason": "no_approved_target_mapping"})
    if profile.business_status == "휴업":
        # 휴업 허용 여부는 공고마다 달라 후보에서 빼지 않는다(자격 판정 단계에서 공고문 기준으로 본다).
        unapplied.append({"source": "company", "field": "business_status", "value": "휴업", "reason": "rule_differs_by_program"})
    if profile.business_start_date is not None:
        # 업력 기준(창업 3년·7년 등)은 공고문마다 달라 정형 필드로 거를 수 없다.
        unapplied.append({"source": "company", "field": "business_start_date", "value": str(profile.business_start_date),
                          "reason": "age_rule_differs_by_program"})
    region, excluded = None, ()
    if profile.region:
        # BOUNDARY: 표준 기업 지역을 공통 후보 필터에 전달한다. 제목 지역·소관기관 우선순위는 region.py가 소유한다.
        excluded = excluded_jurisdictions(profile.region)
        if excluded is None:
            # 표준명이 아닌 예전 자유 입력 값은 어느 광역인지 추측하지 않는다(기업정보에서 다시 고르면 적용된다).
            unapplied.append({"source": "company", "field": "region", "value": profile.region, "reason": "region_not_standard"})
            excluded = ()
        else:
            region = profile.region
    return CompanyConditions(targets, profile.business_status == "폐업", unapplied, region, excluded)


def combine(company, extraction, as_of):
    """기업정보 조건과 질문 조건을 AND로 합친다. 반환: (ProgramCandidateFilter 또는 None, 충돌 정보 또는 None).

    질문이 말한 지원대상과 기업규모로 가능한 지원대상이 겹치지 않으면 조건을 몰래 완화하지 않고 충돌로 돌려준다.
    """
    query_filter = extraction.candidate_filter
    jurisdictions = query_filter.jurisdictions
    if company.excluded_jurisdictions and jurisdictions:
        # 질문이 말한 소관기관 중 기업 지역에서 허용되는 것만 남긴다. 하나도 없으면 완화하지 않고 충돌로 돌려준다.
        jurisdictions = tuple(value for value in jurisdictions if value not in company.excluded_jurisdictions)
        if not jurisdictions:
            return None, {"kind": "region", "company_region": company.region, "query_jurisdictions": list(query_filter.jurisdictions)}
    targets = query_filter.targets
    if company.targets is not None:
        if targets:
            targets = tuple(value for value in targets if value in company.targets)
            if not targets:
                return None, {"kind": "target", "company_targets": list(company.targets), "query_targets": list(query_filter.targets)}
        else:
            targets = company.targets
    return ProgramCandidateFilter(company_region=company.region, categories=query_filter.categories, targets=targets, jurisdictions=jurisdictions,
                                  exclude_jurisdictions=company.excluded_jurisdictions,
                                  not_closed_on=query_filter.not_closed_on, exclude_closed_on=as_of), None


def regional_ranking(programs, region, spec):
    """가까운 의미 검색 결과에만 작은 지역 가산점을 적용하고 원래 순위를 남긴다.

    기준 점수는 기업정보 문장 검색을 합친 경우 blended_score, 아니면 기존 rrf_score다(original_score에 그대로 남는다).
    """
    def base(item):
        return item["blended_score"] if item.get("blended_score") is not None else (item.get("rrf_score") or 0.0)

    best = max((base(item) for item in programs), default=0.0)
    mapping = region_contract()["jurisdiction_regions"]
    standard = region in region_contract()["regions"]
    ranked = []
    for item in programs:
        score = base(item)
        bonus = spec["region_bonus"] if (standard and mapping.get(item.get("jurisdiction_name")) == region
                  and score > 0 and score >= best * spec["minimum_score_ratio"]) else 0.0
        ranked.append(dict(item, original_rank=item["rank"], original_score=score, region_bonus=bonus, final_score=score + bonus))
    ranked.sort(key=lambda item: (-item["final_score"], item["original_rank"]))
    return [dict(item, rank=rank) for rank, item in enumerate(ranked[:TOP_K], 1)]


class PersonalizedSearchService:
    def __init__(self, natural_filter, candidate_service, discovery_factory):
        self.natural_filter, self.candidate_service, self.discovery_factory = natural_filter, candidate_service, discovery_factory

    def search(self, query, profile, as_of):
        company = company_conditions(profile)
        if company.closed_company:
            # 폐업 기업은 신청 주체가 아니다(사용자 승인 규칙). LLM·검색 호출 없이 명확한 상태로 끝낸다.
            return {"status": "COMPANY_CLOSED", "top_k": TOP_K, "as_of": str(as_of), "candidate_count": 0, "programs": [],
                    "natural_filter": None, "applied_conditions": {"company": {"business_status": "폐업"}},
                    "unapplied_conditions": company.unapplied}
        # 질문 조건 추출은 V1·V2 공통 Natural Filter를 그대로 쓴다(LLM 1회, 허용값 enum + 질문 근거 검사).
        extraction = self.natural_filter.extract(query, as_of)
        base = {"top_k": TOP_K, "as_of": str(as_of), "natural_filter": extraction.to_dict(),
                "applied_conditions": {"company": {"targets": list(company.targets) if company.targets else [],
                                                   "region": company.region,
                                                   "excluded_jurisdictions": list(company.excluded_jurisdictions)},
                                       "query": {"categories": list(extraction.candidate_filter.categories),
                                                 "targets": list(extraction.candidate_filter.targets),
                                                 "currently_open": extraction.candidate_filter.not_closed_on is not None},
                                       "exclude_closed_on": str(as_of)},
                "unapplied_conditions": company.unapplied + [{"source": "query", "field": "constraint", "value": item,
                                                              "reason": "not_a_structured_filter"}
                                                             for item in extraction.unapplied_constraints]}
        candidate_filter, conflict = combine(company, extraction, as_of)
        if conflict is not None:
            return dict(base, status="CONDITION_CONFLICT", candidate_count=0, programs=[], conflict=conflict)
        found = self.candidate_service.find_candidates(candidate_filter)
        candidates = found.pblanc_ids
        base["applied_conditions"]["company"]["region_basis"] = found.region_basis
        base["applied_conditions"]["company"]["region_rule"] = "소관기관 기준 / 제목 지역 표시 기준" if company.region else None
        if not candidates:
            return dict(base, status="NO_CANDIDATES", candidate_count=0, programs=[])
        ranking = rag_contract()["personalized_ranking"]
        discovery = self.discovery_factory()
        text, used = company_query(profile, as_of)
        spec = ranking["company_query"]
        generic = generic_question(extraction)
        weight = spec["generic_question_weight"] if generic else spec["company_weight"]
        # 기록에는 사용한 항목 이름·가중치만 남긴다(문장 원문 없음).
        base["applied_conditions"]["company"]["company_query"] = {"applied": text is not None, "fields": used,
                                                                  "weight": weight if text else None, "generic_question": generic}
        if text is None:
            programs = discovery.discover(query, candidates, limit=ranking["candidate_limit"])
        else:
            # 두 검색 모두 같은 후보 scope 안의 공고 순위다. 더 깊게 받아 겹치는 공고를 찾은 뒤 candidate_limit으로 자른다.
            programs = blend_rankings(discovery.discover(query, candidates, limit=spec["depth"]),
                                      discovery.discover(text, candidates, limit=spec["depth"]),
                                      weight, spec["rrf_k"], ranking["candidate_limit"])
        programs = regional_ranking(programs, company.region, ranking)
        return dict(base, status="LISTED" if programs else "NO_INDEXED_PROGRAMS", candidate_count=len(candidates),
                    programs=programs)
