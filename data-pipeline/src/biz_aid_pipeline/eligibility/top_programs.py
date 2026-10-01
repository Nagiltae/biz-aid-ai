"""V2 개인화 검색 Top 3 + 공고별 자격 판정 조합.

조합 로직만 여기 있다. 검색은 `candidates.personalized.PersonalizedSearchService`, 공고 하나의 판정은 기존
`eligibility.service.EligibilityService.evaluate`를 그대로 호출한다(판정 규칙·최종 상태 계산·근거 연결을 복제하지 않는다).
LangGraph 단계에서도 같은 두 서비스를 노드로 재사용할 수 있게 조합과 판정을 분리했다.
"""
from biz_aid_pipeline.candidates.personalized import CompanySearchProfile
from biz_aid_pipeline.config.settings import PipelineError

PROGRAM_FIELDS = ("name", "category", "target", "jurisdiction_name", "executing_org_name", "application_start_date",
                  "application_end_date", "application_period_raw", "announcement_url")


def search_profile(company):
    """판정용 기업정보 snapshot에서 검색에 쓰는 4개 값만 코드로 꺼낸다(V2-1 매핑 입력과 같다)."""
    return CompanySearchProfile(company.company_size, company.business_status, company.region, company.business_start_date)


class PersonalizedEligibilityService:
    def __init__(self, search_service, evaluate_one):
        # evaluate_one(pblanc_id, company_profile, as_of) = 기존 단일 공고 EligibilityService.evaluate
        self.search_service, self.evaluate_one = search_service, evaluate_one

    def run(self, query, company, as_of):
        search = self.search_service.search(query, search_profile(company), as_of)
        evaluations = []
        # BOUNDARY: 검색 순위를 다시 계산하지 않고 Top 3 순서 그대로 판정한다. Ollama 병렬 처리를 가정하지 않고 순차 실행한다.
        for program in search.get("programs", []):
            item = {"rank": program["rank"], "pblanc_id": program["pblanc_id"],
                    "program": {key: program.get(key) for key in PROGRAM_FIELDS}}
            try:
                # 공고마다 그 공고 하나로 범위를 제한한 검색·판정이다(다른 공고 근거는 기존 검증이 거부한다).
                result = self.evaluate_one(program["pblanc_id"], company, as_of)
                evaluations.append(dict(item, evaluation_status="COMPLETED", eligibility=result, error_code=None))
            except PipelineError as error:
                # RISK: 한 공고의 계약 위반·접속 실패를 UNKNOWN이나 성공으로 바꾸지 않는다. 그 공고만 실패로 남기고 계속한다.
                evaluations.append(dict(item, evaluation_status="FAILED", eligibility=None, error_code=str(error)))
            except Exception:
                # 예상하지 못한 예외도 원문(주소·내부 정보)을 싣지 않고 고정 코드로 그 공고만 실패 처리한다.
                evaluations.append(dict(item, evaluation_status="FAILED", eligibility=None,
                                        error_code="eligibility_unexpected_error"))
        return {"search": search, "evaluations": evaluations}
