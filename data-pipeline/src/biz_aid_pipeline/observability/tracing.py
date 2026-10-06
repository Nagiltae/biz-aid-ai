"""LangSmith 선택적 실행 추적(V2-6).

자동 추적(LANGSMITH_TRACING + LangChain/LangGraph callback)은 쓰지 않는다. 자동 추적은 질문·기업정보·prompt·검색 조각·모델 응답을
입력·출력으로 그대로 보내기 때문이다. 대신 이 모듈이 정한 단계만 RunTree로 직접 만들고, 값은 허용 형식(코드·숫자)만 보낸다.

- 추적 단위: workflow HTTP 요청 1개 = 최상위 실행 1개, 그 아래 주요 단계(조건 분석·후보 조회·검색·판정·답변 반영·최종 결과)가 자식 실행이다.
- 여러 요청 연결: State의 trace_key(무작위 값)를 metadata thread_id로 붙여 같은 추천 흐름을 한 묶음(thread)으로 본다. 사용자 ID·기업정보는 쓰지 않는다.
- 장애 격리: 추적 생성·전송 실패는 기록만 하고 무시한다. 전송은 SDK 배경 thread가 하므로 요청을 기다리게 하지 않는다.
"""
import logging
import re
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

from biz_aid_pipeline.config.settings import ROOT, profile_values

log = logging.getLogger(__name__)

SETTING_NAMES = {"BIZAID_TRACING_ENABLED", "LANGSMITH_API_KEY", "LANGSMITH_PROJECT", "LANGSMITH_ENDPOINT"}
# 사용자가 준비한 프로젝트(ID 928ce4c3-…)의 실제 이름이다. 없는 이름으로 보내면 LangSmith가 같은 이름의 새 프로젝트를 자동으로 만든다.
DEFAULT_PROJECT = "biz-aid"
# BOUNDARY: 문자열은 상태·코드·공고 ID·field ID 같은 기계 값만 보낸다. 한글 문장·긴 글(질문·기업명·근거·답변)은 이 형식을 통과하지 못한다.
SAFE_TEXT = re.compile(r"^[A-Za-z0-9_.:,\-]{0,120}$")
REDACTED = "<redacted>"
MAX_LIST = 20


@dataclass(frozen=True)
class TraceSettings:
    enabled: bool
    project: str
    endpoint: str | None
    api_key: str = field(repr=False, default="")

    @classmethod
    def load(cls, root=ROOT, profile="dev", environ=None):
        if profile == "prod":
            # BOUNDARY: 운영에서는 Secret·endpoint를 읽거나 외부 추적 Client를 만들지 않는다.
            return cls(False, DEFAULT_PROJECT, None)
        values = profile_values(root, profile, SETTING_NAMES, environ)
        enabled = values.get("BIZAID_TRACING_ENABLED", "").strip().lower() == "true"
        if profile == "prod":
            # BOUNDARY(IMP-023): 운영 profile은 설정과 관계없이 외부 추적을 보내지 않는다(실사용자 요청의 외부 전송 결정 전).
            enabled = False
        key = values.get("LANGSMITH_API_KEY", "").strip()
        if enabled and not key:
            # 켜져 있어도 키가 없으면 AI 기능은 그대로 두고 추적만 끈다.
            log.warning("tracing disabled: LANGSMITH_API_KEY is not set")
            enabled = False
        return cls(enabled, values.get("LANGSMITH_PROJECT", "").strip() or DEFAULT_PROJECT,
                   values.get("LANGSMITH_ENDPOINT", "").strip() or None, key)


def safe_value(value):
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value if SAFE_TEXT.match(value) else REDACTED
    if isinstance(value, (list, tuple)):
        return [safe_value(item) for item in list(value)[:MAX_LIST] if not isinstance(item, (dict, list, tuple))]
    return REDACTED


def sanitize(values):
    """보낼 값을 한 단계 dict의 허용 형식으로만 남긴다. SDK의 hide_inputs/hide_outputs/hide_metadata에도 같은 함수를 건다(이중 방어)."""
    if not isinstance(values, dict):
        return {}
    return {str(key): safe_value(item) for key, item in values.items() if SAFE_TEXT.match(str(key))}


def safe_metadata(values):
    # SDK가 metadata에 붙이는 내부 값(ls_*)은 형식을 지키므로 그대로 두고 나머지는 같은 규칙으로 거른다.
    return sanitize(values)


def error_code(error):
    """오류는 코드만 남긴다. PipelineError는 원래 코드 문자열이고, 그 밖의 예외는 메시지 없이 클래스 이름만 쓴다."""
    from biz_aid_pipeline.config.settings import PipelineError
    if isinstance(error, PipelineError) and SAFE_TEXT.match(str(error)):
        return str(error)
    return f"unexpected:{type(error).__name__}"


class Tracer:
    """LangSmith Client 하나를 감싼다. 모든 SDK 호출은 실패해도 예외를 밖으로 내지 않는다."""

    def __init__(self, client, project):
        self.client, self.project = client, project
        self._warned = threading.Event()

    def guard(self, action, *args, **kwargs):
        try:
            return action(*args, **kwargs)
        except Exception as error:  # 관측 장애가 추천 기능을 멈추게 하지 않도록 모든 예외를 삼킨다.
            self.failed(error)
            return None

    def failed(self, error):
        # 같은 경고를 요청마다 남기지 않는다. 메시지 원문 대신 예외 종류만 남긴다(응답 본문·헤더 노출 방지).
        if not self._warned.is_set():
            self._warned.set()
            log.warning("tracing failed (%s); AI flow continues", type(error).__name__)

    def flush(self):
        self.guard(self.client.flush)


def build_tracer(settings, session=None):
    """설정이 꺼져 있으면 None(추적 없음). 켜져 있으면 런타임 정보·환경변수 자동 첨부를 끈 Client를 만든다."""
    if not settings.enabled:
        return None
    try:
        from langsmith import Client
        tracer = Tracer(None, settings.project)
        client = Client(api_url=settings.endpoint, api_key=settings.api_key, session=session, auto_batch_tracing=True,
                        omit_traced_runtime_info=True, hide_inputs=sanitize, hide_outputs=sanitize, hide_metadata=safe_metadata,
                        tracing_error_callback=tracer.failed)
        tracer.client = client
        return tracer
    except Exception as error:  # Client 생성 실패도 추적만 끄고 서비스는 계속한다.
        log.warning("tracing disabled: client setup failed (%s)", type(error).__name__)
        return None


class Span:
    def __init__(self, tracer, run):
        self.tracer, self.run, self.outputs = tracer, run, {}

    def record(self, **values):
        self.outputs.update(values)


class NullSpan:
    def record(self, **values):
        pass


NULL_SPAN = NullSpan()
_current = ContextVar("bizaid_trace_span", default=None)


@contextmanager
def _run(tracer, run, outputs_on_exit=True):
    span = Span(tracer, run)
    token = _current.set(span)
    started = time.monotonic()
    try:
        yield span
    except Exception as error:
        tracer.guard(run.end, outputs=sanitize(span.outputs), error=error_code(error))
        tracer.guard(run.patch)
        raise
    else:
        span.outputs.setdefault("elapsed_seconds", round(time.monotonic() - started, 3))
        tracer.guard(run.end, outputs=sanitize(span.outputs))
        tracer.guard(run.patch)
    finally:
        _current.reset(token)


@contextmanager
def workflow_trace(tracer, name, trace_key=None, tags=("bizaid", "workflow"), **inputs):
    """요청 1개의 최상위 실행(workflow·AI 검색). 안에서 LangChain/LangGraph 자동 추적은 항상 끈다(환경변수로 켜져 있어도)."""
    from langsmith import tracing_context
    # BOUNDARY: 자동 추적을 끄는 범위다. 이 안의 ChatOllama·LangGraph 호출은 질문·prompt·State를 외부로 보내지 않는다.
    with tracing_context(enabled=False):
        if tracer is None:
            yield NULL_SPAN
            return
        from langsmith import RunTree
        metadata = {"thread_id": trace_key, "workflow_trace_key": trace_key} if trace_key else {}
        run = tracer.guard(RunTree, name=name, run_type="chain", inputs=sanitize(inputs), project_name=tracer.project,
                           ls_client=tracer.client, extra={"metadata": sanitize(metadata)}, tags=list(tags))
        if run is None:
            yield NULL_SPAN
            return
        tracer.guard(run.post)
        with _run(tracer, run) as span:
            yield span


@contextmanager
def step(name, **inputs):
    """현재 workflow 실행 아래 자식 단계. 추적 중이 아니면 아무것도 하지 않는다."""
    parent = _current.get()
    if parent is None:
        yield NULL_SPAN
        return
    tracer = parent.tracer
    run = tracer.guard(parent.run.create_child, name=name, run_type="chain", inputs=sanitize(inputs))
    if run is None:
        yield NULL_SPAN
        return
    tracer.guard(run.post)
    with _run(tracer, run) as span:
        yield span


def traced(name, function, summarize, describe=None):
    """기존 함수를 고치지 않고 단계 실행으로 감싼다. summarize(결과)·describe(인자)는 허용 값 dict만 돌려준다."""
    def wrapper(*args, **kwargs):
        with step(name, **(describe(*args, **kwargs) if describe else {})) as span:
            result = function(*args, **kwargs)
            span.record(**summarize(result))
            return result
    return wrapper


# 단계별 요약: 결과에서 개수·상태·코드만 꺼낸다(원문·값 없음).
def natural_summary(result):
    applied = result.candidate_filter
    return {"request_mode": result.request_mode, "applied_categories": len(applied.categories), "applied_targets": len(applied.targets),
            "currently_open": applied.not_closed_on is not None, "unapplied_count": len(result.unapplied_constraints),
            "discarded_count": len(result.discarded)}


def candidates_summary(result):
    return {"candidate_count": len(result.pblanc_ids)}


def discovery_summary(result):
    return {"program_count": len(result)}


def search_summary(result):
    # BOUNDARY(IMP-019): 기업정보 검색 문장·항목 값은 보내지 않고 적용 여부만 보낸다.
    company_query = ((result.get("applied_conditions") or {}).get("company") or {}).get("company_query") or {}
    return {"status": result.get("status"), "candidate_count": result.get("candidate_count"), "program_count": len(result.get("programs") or []),
            "company_query_applied": bool(company_query.get("applied"))}


def eligibility_summary(result):
    criteria = result.get("criteria") or []
    return {"pblanc_id": result.get("pblanc_id"), "status": result.get("status"), "criteria_count": len(criteria),
            "citation_count": sum(len(item.get("citations") or []) for item in criteria),
            "missing_count": len(result.get("missing_information") or []), "llm_seconds": result.get("llm_seconds")}


def query_summary(result):
    """AI 검색(V1 질문) 결과 요약: 질문 유형·상태·개수만(질문·답변 문장·공고명 없음)."""
    return {"request_mode": result.get("request_mode"), "status": result.get("status"), "candidate_count": result.get("candidate_count"),
            "program_count": len(result.get("programs") or []), "citation_count": len(result.get("citations") or []),
            "has_answer": bool(result.get("answer"))}


def state_summary(state):
    evaluations = state.get("evaluations") or []
    final = state.get("final_result") or {}
    return {"status": state.get("status"), "current_step": state.get("current_step"), "next_action": state.get("next_action"),
            "round": state.get("round"), "pending_count": len(state.get("pending") or []), "evaluation_count": len(evaluations),
            "completed_count": sum(item.get("evaluation_status") == "COMPLETED" for item in evaluations),
            "failed_count": sum(item.get("evaluation_status") == "FAILED" for item in evaluations),
            "missing_field_count": len(state.get("missing_information") or []), "failure_code": state.get("failure_code"),
            **{f"final_{key}": value for key, value in (final.get("counts") or {}).items()}}
