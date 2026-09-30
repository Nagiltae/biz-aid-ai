"""FastAPI 내부 API v1. handler는 요청 검증 → ServiceRuntime 호출 → 결과 직렬화만 한다.

판단 로직(후보·검색·RAG·자격 판정)은 기존 서비스에 있고 여기서 다시 구현하지 않는다.
NO_CANDIDATES·INSUFFICIENT_EVIDENCE·NEEDS_MORE_INFO·INELIGIBLE 같은 결과는 정상 판단이라 HTTP 200으로 돌려준다.
"""
from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from biz_aid_pipeline.config.settings import PipelineError

# 모델 출력이 계약을 어긴 경우(외부 LLM 응답 문제)는 502, 의존 서비스 접속 실패는 503이다.
MODEL_OUTPUT_ERRORS = ("filter_extraction_", "eligibility_output_", "eligibility_invalid_evidence_id",
                       "eligibility_cross_program_evidence", "eligibility_unknown_profile_field", "rag_llm_output_")


class QueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    as_of: date | None = None


class EligibilityRequest(BaseModel):
    pblanc_id: str = Field(pattern=r"^PBLN_[0-9]{12,20}$")
    as_of: date | None = None
    company_profile: dict = Field(description="eligibility.profile.CompanyProfileSnapshot 필드(모두 선택)")


def status_for(code):
    if code == "eligibility_program_not_found_or_inactive":
        return 404
    if code.startswith("company_profile_"):
        return 422
    if code == "llm_unavailable" or code.startswith("llm_http_error"):
        return 503
    if code.startswith(MODEL_OUTPUT_ERRORS):
        return 502
    return 500


def create_app(runtime_factory=None):
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

    @app.post("/internal/v1/query")
    def query(body: QueryRequest, request: Request):
        return request.app.state.runtime.answer_query(body.query, body.as_of)

    @app.post("/internal/v1/eligibility")
    def eligibility(body: EligibilityRequest, request: Request):
        from biz_aid_pipeline.eligibility.profile import CompanyProfileSnapshot
        company = CompanyProfileSnapshot.from_dict(body.company_profile)
        return request.app.state.runtime.evaluate_eligibility(body.pblanc_id, company, body.as_of)

    return app


app = create_app()
