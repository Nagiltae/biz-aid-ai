"""LLM 호출 경계. RagService·필터 추출·자격 판정은 LlmProvider만 알고 특정 모델 API를 모른다.

WHY: provider를 바꿔도(Ollama → Bedrock 등) orchestration·prompt·retrieval 계약은 그대로여야 한다.
provider는 공통 LlmRequest(system, user, 출력 JSON schema)를 받아 LlmResponse(text, 모델 정보, 시간)를 돌려주는 일만 한다.
BOUNDARY: LangChain은 이 파일(LLM 호출 계층)에서만 쓴다. 후보 필터·검색·RRF·근거 연결·자격 상태 계산은 LangChain이 소유하지 않는다.
"""
import json
import os
import time
from dataclasses import dataclass, field
from typing import Protocol

from biz_aid_pipeline.config.settings import ROOT, PipelineError, profile_values, read_json

SETTING_NAMES = {"LLM_PROVIDER", "OLLAMA_BASE_URL", "OLLAMA_MODEL", "OLLAMA_TIMEOUT_SECONDS", "OLLAMA_KEEP_ALIVE"}


@dataclass(frozen=True)
class LlmRequest:
    system: str
    user: str
    output_schema: dict
    temperature: float = 0.0
    # 생성 token 상한(num_predict). None이면 모델 기본값이다. 반복 생성 폭주를 막아야 하는 호출(자격 판정)이 정한다.
    max_output_tokens: int | None = None


@dataclass(frozen=True)
class LlmResponse:
    text: str
    provider: str
    model: str
    elapsed_seconds: float
    usage: dict = field(default_factory=dict)


class LlmProvider(Protocol):
    name: str
    model: str

    def generate(self, request: LlmRequest) -> LlmResponse: ...


def chat_prompt():
    """system·user 두 메시지 prompt. 값은 변수로 넣어 본문 안의 JSON 중괄호가 template 문법으로 해석되지 않게 한다."""
    from langchain_core.prompts import ChatPromptTemplate
    return ChatPromptTemplate.from_messages([("system", "{system}"), ("human", "{user}")])


class OllamaLlmProvider:
    """LangChain ChatOllama로 로컬 Ollama를 호출한다. 모델 적재·종료 같은 Ollama process 수명은 관리하지 않는다.

    구조화 출력: 요청마다 받은 JSON schema(허용값 enum 포함)를 Ollama format으로 넘겨 생성 단계에서 형식을 제한한다.
    그래도 결과는 문자열로 돌려주고, 형식·허용값 재검증은 각 서비스의 application 코드가 그대로 한다(이중 방어).
    """

    name = "ollama"

    def __init__(self, base_url, model, timeout_seconds, keep_alive, chat=None, num_ctx=None):
        self.base_url, self.model = base_url.rstrip("/"), model
        self.timeout_seconds, self.keep_alive, self.num_ctx = timeout_seconds, keep_alive, num_ctx
        if chat is None:
            from langchain_ollama import ChatOllama
            # WHY: 추론 과정(thinking)은 답변 근거가 아니고 지연만 늘려 끈다(reasoning=False). temperature는 요청마다 넘긴다.
            chat = ChatOllama(model=model, base_url=self.base_url, keep_alive=keep_alive, reasoning=False,
                              client_kwargs={"timeout": timeout_seconds})
        self.prompt, self.chat = chat_prompt(), chat

    def generate(self, request):
        messages = self.prompt.format_messages(system=request.system, user=request.user)
        # BOUNDARY: options를 넘기면 ChatOllama는 객체의 다른 생성 설정을 쓰지 않으므로 context·출력 상한도 여기에 함께 넣는다.
        options = {"temperature": request.temperature}
        if self.num_ctx:
            options["num_ctx"] = self.num_ctx
        if request.max_output_tokens:
            options["num_predict"] = request.max_output_tokens
        started = time.monotonic()
        deadline = started + self.timeout_seconds
        message, stream = None, None
        try:
            # WHY: client timeout은 읽기 사이의 대기 시간이라 token이 계속 오면 끝나지 않는다(Spring이 포기한 뒤에도 생성이 이어짐).
            # stream으로 받으며 전체 기한을 직접 확인하고, 넘으면 연결을 닫아 Ollama 생성도 멈추게 한다.
            stream = self.chat.stream(messages, format=request.output_schema, options=options)
            for chunk in stream:
                message = chunk if message is None else message + chunk
                if time.monotonic() > deadline:
                    raise PipelineError("llm_timeout")
        except PipelineError:
            raise
        except Exception as error:
            raise PipelineError(error_code(error)) from None
        finally:
            if stream is not None and hasattr(stream, "close"):
                stream.close()
        if message is None:
            raise PipelineError("llm_empty_response")
        elapsed = time.monotonic() - started
        metadata = getattr(message, "response_metadata", {}) or {}
        usage = {key: metadata.get(key) for key in ("prompt_eval_count", "eval_count", "total_duration", "load_duration", "done_reason")}
        content = message.content if isinstance(message.content, str) else json.dumps(message.content, ensure_ascii=False)
        return LlmResponse(content, self.name, metadata.get("model", self.model), round(elapsed, 2), usage)


def error_code(error):
    """LangChain·Ollama client 예외를 고정 코드로 바꾼다. 원문 메시지(주소·모델 상세)는 응답·로그에 싣지 않는다."""
    status = getattr(error, "status_code", None)
    if isinstance(status, int) and status >= 400:
        return f"llm_http_error:{status}"
    # 첫 token 전까지 응답이 없어 읽기 대기가 기한(timeout_seconds)을 넘은 경우도 시간 초과다.
    if "timeout" in type(error).__name__.lower():
        return "llm_timeout"
    return "llm_unavailable"


def llm_call_limits(root=ROOT):
    """내부 API 계약의 LLM 호출 상한(전체 기한 초, context token 수). Spring 응답 제한보다 짧아야 한다."""
    spec = read_json(root / "contracts/schemas/internal-api.contract.json")["llm_call"]
    return float(spec["deadline_seconds"]), int(spec["context_tokens"])


def provider_from_settings(profile, root=ROOT, environ=None):
    """설정(LLM_PROVIDER 등)으로 provider를 고른다. 새 provider는 여기에만 분기를 추가한다."""
    if profile != "dev":
        raise PipelineError("rag_requires_dev_profile")
    settings = profile_values(root, profile, SETTING_NAMES, os.environ if environ is None else environ)
    provider = settings.get("LLM_PROVIDER") or "ollama"
    if provider == "ollama":
        model = settings.get("OLLAMA_MODEL")
        if not model:
            raise PipelineError("ollama_model_required")
        deadline, num_ctx = llm_call_limits()
        # BOUNDARY: 설정(OLLAMA_TIMEOUT_SECONDS)은 기한을 줄일 수만 있다. Spring 응답 제한(90초)보다 길게 생성하지 않는다.
        timeout = min(float(settings.get("OLLAMA_TIMEOUT_SECONDS") or deadline), deadline)
        return OllamaLlmProvider(settings.get("OLLAMA_BASE_URL") or "http://127.0.0.1:11434", model, timeout,
                                 settings.get("OLLAMA_KEEP_ALIVE") or "10m", num_ctx=num_ctx)
    raise PipelineError("llm_provider_unsupported:" + provider)
