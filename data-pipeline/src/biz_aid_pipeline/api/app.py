"""FastAPI 내부 API v1. handler는 요청 검증 → ServiceRuntime 호출 → 결과 직렬화만 한다.

판단 로직(후보·검색·RAG·자격 판정)은 기존 서비스에 있고 여기서 다시 구현하지 않는다.
NO_CANDIDATES·INSUFFICIENT_EVIDENCE·NEEDS_MORE_INFO·INELIGIBLE 같은 결과는 정상 판단이라 HTTP 200으로 돌려준다.
"""
import hmac
from contextlib import asynccontextmanager
from datetime import date

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from biz_aid_pipeline.config.settings import ROOT, PipelineError, profile_values

INTERNAL_KEY_HEADER = "X-Internal-Api-Key"

# 모델 출력이 계약을 어긴 경우(외부 LLM 응답 문제)는 502, 의존 서비스 접속 실패는 503이다.
MODEL_OUTPUT_ERRORS = ("filter_extraction_", "eligibility_output_", "eligibility_invalid_evidence_id",
                       "eligibility_cross_program_evidence", "eligibility_unknown_profile_field", "rag_llm_output_")


class QueryRequest(BaseModel):
    company_region: str | None = Field(default=None, max_length=80)
    selected_pblanc_id: str | None = Field(default=None, pattern=r"^PBLN_[0-9]{12,20}$")
    query: str = Field(min_length=1, max_length=2000)
    as_of: date | None = None


class EligibilityRequest(BaseModel):
    pblanc_id: str = Field(pattern=r"^PBLN_[0-9]{12,20}$")
    as_of: date | None = None
    company_profile: dict = Field(description="eligibility.profile.CompanyProfileSnapshot 필드(모두 선택)")


class PersonalizedEligibilityRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    as_of: date | None = None
    company_profile: dict = Field(description="eligibility.profile.CompanyProfileSnapshot 필드(모두 선택)")


class WorkflowStartRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    as_of: date | None = None
    company_profile: dict = Field(description="eligibility.profile.CompanyProfileSnapshot 필드(저장된 값만)")


class WorkflowAdvanceRequest(BaseModel):
    state: dict = Field(description="Spring이 ai_workflows에 저장해 둔 State JSON 그대로")
    command: str = Field(pattern=r"^(continue|answer)$")
    answers: dict = Field(default_factory=dict, description="command=answer일 때 부족 정보 field ID: 값")


class PersonalizedSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    as_of: date | None = None
    company_profile: dict = Field(description="candidates.personalized.CompanySearchProfile 필드(모두 선택)")


def status_for(code):
    if code in ("eligibility_program_not_found_or_inactive", "query_program_not_found_or_inactive"):
        return 404
    # 흐름 상태와 맞지 않는 요청(이미 완료된 workflow 진행, 묻지 않은 field 답변 등)은 요청 쪽 문제다.
    if code.startswith("workflow_"):
        return 409 if code.startswith("workflow_invalid_transition") else 422
    if code.startswith(("company_profile_", "company_search_profile_")):
        return 422
    # 시간 초과(llm_timeout)도 일시적인 의존 서비스 문제다. Spring은 503을 "AI 서비스 일시 불가"로 보여 준다.
    if code in ("llm_unavailable", "llm_timeout") or code.startswith("llm_http_error"):
        return 503
    if code == "llm_empty_response":
        return 502
    if code.startswith(MODEL_OUTPUT_ERRORS):
        return 502
    return 500


class InternalAuthError(Exception):
    def __init__(self, code, status):
        super().__init__(code)
        self.code, self.status = code, status


def internal_api_key():
    """서비스 간 인증(Service-to-Service Authentication) 공유 키. OS 환경변수 우선, 없으면 .env.dev에서 읽는다."""
    return profile_values(ROOT, "dev", {"INTERNAL_AI_API_KEY"}).get("INTERNAL_AI_API_KEY") or None


def create_app(runtime_factory=None, api_key=None):
    key = api_key if api_key is not None else internal_api_key()

    def require_internal_key(request: Request):
        # BOUNDARY: /internal/v1/*는 서비스 계층(Spring)만 부른다. loopback 바인딩에 더해 공유 키로 호출자를 확인한다.
        # 키가 설정되지 않았으면 열어 두지 않고 거부한다(fail closed). 응답에는 키·설정 상세를 싣지 않는다.
        if not key:
            raise InternalAuthError("internal_auth_not_configured", 503)
        supplied = request.headers.get(INTERNAL_KEY_HEADER, "")
        if not hmac.compare_digest(supplied.encode(), key.encode()):
            raise InternalAuthError("internal_auth_failed", 401)

    @asynccontextmanager
    async def lifespan(app):
        # 서버 시작 때 공통 의존 객체를 한 번 만들고, 종료 때 DB pool·Qdrant client를 닫는다. Ollama 서버는 관리하지 않는다.
        if runtime_factory is None:
            from biz_aid_pipeline.runtime import ServiceRuntime
            app.state.runtime = ServiceRuntime("dev")
        else:
            app.state.runtime = runtime_factory()
        try:
            yield
        finally:
            app.state.runtime.close()

    app = FastAPI(title="BizAid internal AI API", version="1", lifespan=lifespan)

    @app.exception_handler(InternalAuthError)
    async def internal_auth_error(request, error):
        return JSONResponse(status_code=error.status, content={"error": {"code": error.code}})

    @app.exception_handler(PipelineError)
    async def pipeline_error(request, error):
        # RISK: 내부 stack trace·연결 정보를 응답에 싣지 않는다. 고정된 오류 code만 돌려준다.
        return JSONResponse(status_code=status_for(str(error)), content={"error": {"code": str(error)}})

    from qdrant_client.http.exceptions import ResponseHandlingException
    from sqlalchemy.exc import OperationalError

    @app.exception_handler(OperationalError)
    @app.exception_handler(ResponseHandlingException)
    async def dependency_error(request, error):
        return JSONResponse(status_code=503, content={"error": {"code": "dependency_unavailable"}})

    @app.exception_handler(Exception)
    async def unexpected_error(request, error):
        return JSONResponse(status_code=500, content={"error": {"code": "internal_error"}})

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/internal/v1/query", dependencies=[Depends(require_internal_key)])
    def query(body: QueryRequest, request: Request):
        options = {}
        if body.selected_pblanc_id is not None:
            options["selected_pblanc_id"] = body.selected_pblanc_id
        if body.company_region is not None:
            options["company_region"] = body.company_region
        return request.app.state.runtime.answer_query(body.query, body.as_of, **options)

    @app.post("/internal/v1/eligibility", dependencies=[Depends(require_internal_key)])
    def eligibility(body: EligibilityRequest, request: Request):
        from biz_aid_pipeline.eligibility.profile import CompanyProfileSnapshot
        company = CompanyProfileSnapshot.from_dict(body.company_profile)
        return request.app.state.runtime.evaluate_eligibility(body.pblanc_id, company, body.as_of)

    @app.post("/internal/v2/personalized-search", dependencies=[Depends(require_internal_key)])
    def personalized_search(body: PersonalizedSearchRequest, request: Request):
        # V1 /internal/v1/query와 의미가 달라(기업정보 조건 결합, Top 3, 종료 공고 제외) 별도 V2 계약으로 둔다.
        from biz_aid_pipeline.candidates.personalized import CompanySearchProfile
        profile = CompanySearchProfile.from_dict(body.company_profile)
        return request.app.state.runtime.personalized_search(body.query, profile, body.as_of)

    @app.post("/internal/v2/personalized-eligibility", dependencies=[Depends(require_internal_key)])
    def personalized_eligibility(body: PersonalizedEligibilityRequest, request: Request):
        # 개인화 검색 Top 3 → 공고별 판정을 서버가 조합한다. 클라이언트가 공고를 하나씩 돌며 AI 흐름을 소유하지 않게 한다.
        from biz_aid_pipeline.eligibility.profile import CompanyProfileSnapshot
        company = CompanyProfileSnapshot.from_dict(body.company_profile)
        return request.app.state.runtime.personalized_eligibility(body.query, company, body.as_of)

    @app.post("/internal/v2/workflows/start", dependencies=[Depends(require_internal_key)])
    def workflow_start(body: WorkflowStartRequest, request: Request):
        # 시작 단계는 개인화 검색과 Top 3 확정까지만 한다(판정 LLM 없음). State는 Spring이 MySQL에 저장한다.
        from biz_aid_pipeline.eligibility.profile import CompanyProfileSnapshot
        CompanyProfileSnapshot.from_dict(body.company_profile)
        return {"state": request.app.state.runtime.workflow_start(body.query, body.company_profile, body.as_of)}

    @app.post("/internal/v2/workflows/advance", dependencies=[Depends(require_internal_key)])
    def workflow_advance(body: WorkflowAdvanceRequest, request: Request):
        # BOUNDARY: DB를 읽지 않고 받은 State로 한 단계만 실행한다. 다음 행동은 State가 정한다(판정은 최대 1건).
        return {"state": request.app.state.runtime.workflow_advance(body.state, body.command, body.answers)}

    return app


app = create_app()
