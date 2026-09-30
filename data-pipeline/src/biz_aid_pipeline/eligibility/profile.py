"""Eligibility 입력용 기업 Profile snapshot. AI 계층이 받는 그 시점의 값일 뿐 저장·관리하지 않는다.

WHY: 기업 정보의 source of truth는 이후 서비스 계층(Spring Boot)이다. 여기서는 영구 저장·schema를 만들지 않는다.
모든 field는 선택이며 값이 없으면 해당 조건은 UNKNOWN이다. 필드는 PROJECT_DESIGN §10 기업 프로필과
공고 자격요건에 실제로 나오는 값(사업자 형태·신용점수·체납·휴폐업)만 둔다. 공고별 특수 사실은 additional_facts로 받는다.
"""
from dataclasses import asdict, dataclass, field, fields
from datetime import date

from biz_aid_pipeline.config.settings import PipelineError

ENTITY_TYPES = ("개인사업자", "법인")
BUSINESS_STATUSES = ("영업중", "휴업", "폐업")


@dataclass(frozen=True)
class CompanyProfileSnapshot:
    company_name: str | None = None          # 표시용
    business_entity_type: str | None = None  # 개인사업자 / 법인 (공고 대상 구분)
    company_size: str | None = None          # 기업형태: 소상공인·중소기업·중견기업 등
    region: str | None = None                # 사업장 소재지
    industry: str | None = None              # 업종(표준산업분류명 또는 코드)
    business_start_date: date | None = None  # 개업일. 업력은 application이 계산한다
    business_status: str | None = None       # 영업중 / 휴업 / 폐업
    employee_count: int | None = None        # 상시근로자 수
    annual_revenue_krw: int | None = None    # 최근 연 매출(원)
    credit_score: int | None = None          # 대표자 개인신용점수(NCB 등)
    tax_delinquent: bool | None = None       # 국세·지방세 체납 중 여부
    venture_certified: bool | None = None    # 벤처기업 확인 여부
    research_institute: bool | None = None   # 기업부설연구소 보유 여부
    exporter: bool | None = None             # 수출기업 여부
    additional_facts: dict = field(default_factory=dict)  # 공고별 특수 사실 {이름: 값}. 예: {"최근 2개월 매출(원)": 5000000}

    @classmethod
    def from_dict(cls, value):
        known = {item.name for item in fields(cls)}
        unknown = sorted(set(value) - known)
        if unknown:
            raise PipelineError("company_profile_unknown_field:" + ",".join(unknown))
        data = dict(value)
        try:
            if data.get("business_start_date"):
                data["business_start_date"] = date.fromisoformat(data["business_start_date"])
        except (TypeError, ValueError):
            raise PipelineError("company_profile_invalid:business_start_date") from None
        for name, allowed in (("business_entity_type", ENTITY_TYPES), ("business_status", BUSINESS_STATUSES)):
            if data.get(name) is not None and data[name] not in allowed:
                raise PipelineError(f"company_profile_invalid:{name}")
        for name in ("employee_count", "annual_revenue_krw", "credit_score"):
            if data.get(name) is not None and (not isinstance(data[name], int) or isinstance(data[name], bool)):
                raise PipelineError(f"company_profile_invalid:{name}")
        for name in ("tax_delinquent", "venture_certified", "research_institute", "exporter"):
            if data.get(name) is not None and not isinstance(data[name], bool):
                raise PipelineError(f"company_profile_invalid:{name}")
        if not isinstance(data.get("additional_facts", {}), dict) or not all(
                isinstance(v, (str, int, float, bool)) for v in data.get("additional_facts", {}).values()):
            raise PipelineError("company_profile_invalid:additional_facts")
        return cls(**data)

    def business_age_months(self, as_of):
        if self.business_start_date is None:
            return None
        start = self.business_start_date
        return (as_of.year - start.year) * 12 + as_of.month - start.month - (1 if as_of.day < start.day else 0)

    def facts(self, as_of):
        """LLM과 검증이 함께 쓰는 사실 목록 {field 이름: 값 또는 None}. 업력은 application이 계산한 파생 값이다."""
        values = {key: value for key, value in asdict(self).items() if key != "additional_facts"}
        values["business_start_date"] = str(self.business_start_date) if self.business_start_date else None
        values["business_age_months"] = self.business_age_months(as_of)
        values.update({f"additional_facts.{key}": value for key, value in self.additional_facts.items()})
        return values
