"""RAG가 쓰는 LLM 호출 경계. RagService는 LlmProvider만 알고 특정 모델 API를 모른다.

WHY: provider를 바꿔도(Ollama → Gemini 등) RAG orchestration·prompt·retrieval 계약은 그대로여야 한다.
provider는 공통 LlmRequest(system, user, 출력 JSON schema)를 받아 LlmResponse(text, 모델 정보, 시간)를 돌려주는 일만 한다.
"""
import json
import os
import time
from dataclasses import dataclass, field
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

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


class OllamaLlmProvider:
    """로컬 Ollama `/api/chat` 호출. 모델 적재·종료 같은 Ollama process 수명은 관리하지 않는다."""

    name = "ollama"

    def __init__(self, base_url, model, timeout_seconds, keep_alive, opener=urlopen):
        self.base_url, self.model = base_url.rstrip("/"), model
        self.timeout_seconds, self.keep_alive, self.opener = timeout_seconds, keep_alive, opener

    def generate(self, request):
        body = {"model": self.model, "stream": False, "keep_alive": self.keep_alive,
                "messages": [{"role": "system", "content": request.system}, {"role": "user", "content": request.user}],
                # WHY: 구조화 출력은 JSON schema로 강제한다. 추론 과정(thinking)은 답변 근거가 아니고 지연만 늘려 끈다.
                "format": request.output_schema, "think": False, "options": {"temperature": request.temperature}}
        started = time.monotonic()
        try:
            with self.opener(Request(self.base_url + "/api/chat", data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json"}), timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read())
        except HTTPError as error:
            raise PipelineError(f"llm_http_error:{error.code}") from None
        except (URLError, TimeoutError, OSError):
            raise PipelineError("llm_unavailable") from None
        elapsed = time.monotonic() - started
        usage = {key: payload.get(key) for key in ("prompt_eval_count", "eval_count", "total_duration", "load_duration")}
        return LlmResponse(payload.get("message", {}).get("content", ""), self.name, payload.get("model", self.model),
                           round(elapsed, 2), usage)


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
