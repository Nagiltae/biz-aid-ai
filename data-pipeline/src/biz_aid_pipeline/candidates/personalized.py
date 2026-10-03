"""V2 기업정보 기반 개인화 검색: 기업정보 조건(코드) + 질문 조건(Natural Filter) → MySQL 후보 → 공고 단위 검색 Top 3.

BOUNDARY: 기업정보는 Spring이 소유하고 요청 때 snapshot으로 받는다. 여기서 users·companies 테이블을 읽지 않는다.
저장된 기업정보의 확실한 사실만 일반 코드로 검색조건이 된다. LLM은 기업정보를 해석하지 않는다(질문 조건 추출만 한다).
의미가 확실하지 않은 값(업력, 휴업 등)은 Hard Filter로 추측하지 않고 unapplied로 드러낸다.
지역은 2026-10-03 사용자 결정으로 "다른 광역 지자체 소관 공고만 제외"한다(매핑은 company-region 계약, candidates/region.py).
"""
from dataclasses import dataclass, fields
from datetime import date

from biz_aid_pipeline.candidates.region import excluded_jurisdictions
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
    """개인화 검색에 필요한 기업정보만 담은 snapshot. 모두 선택값이다."""

    company_size: str | None = None
    business_status: str | None = None
    region: str | None = None
    business_start_date: date | None = None

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
        return cls(**data)


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
        # BOUNDARY: 다른 광역 지자체 소관 공고만 뺀다. 중앙부처·매핑에 없는 소관기관은 전국 대상일 수 있어 남긴다(fail-open).
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
    return ProgramCandidateFilter(categories=query_filter.categories, targets=targets, jurisdictions=jurisdictions,
                                  exclude_jurisdictions=company.excluded_jurisdictions,
                                  not_closed_on=query_filter.not_closed_on, exclude_closed_on=as_of), None


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
        candidates = self.candidate_service.find_candidates(candidate_filter).pblanc_ids
        if not candidates:
            return dict(base, status="NO_CANDIDATES", candidate_count=0, programs=[])
        programs = self.discovery_factory().discover(query, candidates, limit=TOP_K)
        return dict(base, status="LISTED" if programs else "NO_INDEXED_PROGRAMS", candidate_count=len(candidates),
                    programs=programs)
