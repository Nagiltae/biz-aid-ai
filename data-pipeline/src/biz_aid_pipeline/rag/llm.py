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

from biz_aid_pipeline.config.settings import ROOT, PipelineError, profile_values

SETTING_NAMES = {"LLM_PROVIDER", "OLLAMA_BASE_URL", "OLLAMA_MODEL", "OLLAMA_TIMEOUT_SECONDS", "OLLAMA_KEEP_ALIVE"}


@dataclass(frozen=True)
class LlmRequest:
    system: str
    user: str
    output_schema: dict
    temperature: float = 0.0


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

    def __init__(self, base_url, model, timeout_seconds, keep_alive, chat=None):
        self.base_url, self.model = base_url.rstrip("/"), model
        self.timeout_seconds, self.keep_alive = timeout_seconds, keep_alive
        if chat is None:
            from langchain_ollama import ChatOllama
            # WHY: 추론 과정(thinking)은 답변 근거가 아니고 지연만 늘려 끈다(reasoning=False). temperature는 요청마다 넘긴다.
            chat = ChatOllama(model=model, base_url=self.base_url, keep_alive=keep_alive, reasoning=False,
                              client_kwargs={"timeout": timeout_seconds})
        self.prompt, self.chat = chat_prompt(), chat

    def generate(self, request):
        messages = self.prompt.format_messages(system=request.system, user=request.user)
        started = time.monotonic()
        try:
            message = self.chat.invoke(messages, format=request.output_schema, options={"temperature": request.temperature})
        except Exception as error:
            raise PipelineError(error_code(error)) from None
        elapsed = time.monotonic() - started
        metadata = getattr(message, "response_metadata", {}) or {}
        usage = {key: metadata.get(key) for key in ("prompt_eval_count", "eval_count", "total_duration", "load_duration")}
        content = message.content if isinstance(message.content, str) else json.dumps(message.content, ensure_ascii=False)
        return LlmResponse(content, self.name, metadata.get("model", self.model), round(elapsed, 2), usage)


def error_code(error):
    """LangChain·Ollama client 예외를 고정 코드로 바꾼다. 원문 메시지(주소·모델 상세)는 응답·로그에 싣지 않는다."""
    status = getattr(error, "status_code", None)
    if isinstance(status, int) and status >= 400:
        return f"llm_http_error:{status}"
    return "llm_unavailable"


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
        return OllamaLlmProvider(settings.get("OLLAMA_BASE_URL") or "http://127.0.0.1:11434", model,
                                 float(settings.get("OLLAMA_TIMEOUT_SECONDS") or 300), settings.get("OLLAMA_KEEP_ALIVE") or "10m")
    raise PipelineError("llm_provider_unsupported:" + provider)
