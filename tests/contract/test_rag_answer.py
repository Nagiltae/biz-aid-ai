import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data-pipeline/src"))

from biz_aid_pipeline.rag.llm import LlmResponse
from biz_aid_pipeline.rag.service import RagService
from biz_aid_pipeline.retrieval.retriever import SearchResult


def result(rank, chunk_id, pblanc_id, text, pages=(3,)):
    return SearchResult(rank=rank, mode="hybrid", score=0.03, chunk_id=chunk_id, pblanc_id=pblanc_id, title=f"지원사업 공고 {rank}",
                        text=text, heading_path=["2. 지원 요건"], source_sha256="a" * 64, source_format="PDF", route="DOCLING_PDF",
                        parse_key="b" * 64, chunk_set_key="c" * 64, chunk_index=rank, pages=list(pages),
                        provenance=[{"page": pages[0] if pages else None, "bbox_pt": [1, 2, 3, 4]}], embedding_key="e" * 64)


class FakeRetriever:
    def __init__(self, results):
        self.results, self.calls = results, []

    def search(self, query, mode, top_k, pblanc_ids=None):
        self.calls.append((query, mode, top_k) if pblanc_ids is None else (query, mode, top_k, tuple(pblanc_ids)))
        return self.results


class FakeProvider:
    name, model = "fake", "fake-1"

    def __init__(self, output):
        self.output, self.requests = output, []

    def generate(self, request):
        self.requests.append(request)
        return LlmResponse(json.dumps(self.output, ensure_ascii=False), self.name, self.model, 0.1)


RESULTS = [result(1, "chunk-1", "PBLN_1", "업력 6개월 이상 개인사업자"), result(2, "chunk-2", "PBLN_2", "보증한도 900만원")]


class RagAnswerContractTests(unittest.TestCase):
    def test_citations_are_resolved_by_the_application_from_retrieved_results(self):
        retriever = FakeRetriever(RESULTS)
        provider = FakeProvider({"answer": "보증한도는 900만원입니다.", "evidence_ids": ["E2"], "insufficient_evidence": False})
        answer = RagService(retriever, provider).answer("보증한도는?")
        # 적재·평가 baseline과 같은 hybrid top_k 5로 검색한다.
        self.assertEqual(retriever.calls, [("보증한도는?", "hybrid", 5)])
        self.assertEqual((answer.status, answer.used_evidence_ids), ("ANSWERED", ["E2"]))
        citation = answer.citations[0]
        self.assertEqual((citation.chunk_id, citation.pblanc_id, citation.pages, citation.rank), ("chunk-2", "PBLN_2", [3], 2))
        # BOUNDARY: LLM에는 evidence id와 읽을 내용만 가고 식별자·원본 provenance는 가지 않는다.
        prompt = provider.requests[0].user
        self.assertIn("[E2]", prompt)
        # 이번 context의 evidence 번호만 고를 수 있게 생성 단계에서 제한한다.
        self.assertEqual(provider.requests[0].output_schema["properties"]["evidence_ids"]["items"]["enum"],
                         [f"E{n}" for n in range(1, len(RESULTS) + 1)])
        for leaked in ("chunk-2", "PBLN_2", "a" * 64, "b" * 64, "bbox_pt"):
            self.assertNotIn(leaked, prompt)

    def test_unknown_evidence_ids_never_become_citations(self):
        provider = FakeProvider({"answer": "지원 가능합니다.", "evidence_ids": ["E9", "chunk-1"], "insufficient_evidence": False})
        answer = RagService(FakeRetriever(RESULTS), provider).answer("지원 가능한가?")
        # 유효한 근거가 하나도 없으면 답을 근거 기반으로 내보내지 않는다.
        self.assertEqual((answer.status, answer.citations, answer.rejected_evidence_ids), ("INSUFFICIENT_EVIDENCE", [], ["E9", "chunk-1"]))
        self.assertEqual(answer.discarded_answer, "지원 가능합니다.")
        mixed = RagService(FakeRetriever(RESULTS), FakeProvider(
            {"answer": "업력 6개월 이상입니다.", "evidence_ids": ["E1", "E7"], "insufficient_evidence": False})).answer("업력?")
        self.assertEqual(([c.chunk_id for c in mixed.citations], mixed.rejected_evidence_ids), (["chunk-1"], ["E7"]))

    def test_insufficient_evidence_returns_fixed_message_without_citations(self):
        provider = FakeProvider({"answer": "근거가 없습니다.", "evidence_ids": ["E1"], "insufficient_evidence": True})
        answer = RagService(FakeRetriever(RESULTS), provider).answer("신청 마감일은?")
        self.assertEqual((answer.status, answer.answer, answer.citations), ("INSUFFICIENT_EVIDENCE", "제공된 공고문 근거만으로는 확인할 수 없습니다.", []))
        empty = RagService(FakeRetriever([]), FakeProvider(
            {"answer": "없음", "evidence_ids": [], "insufficient_evidence": True})).answer("아무 질문")
        self.assertEqual((empty.status, empty.retrieved), ("INSUFFICIENT_EVIDENCE", []))

    def test_candidate_scope_short_circuits_when_empty_and_rejects_leaks(self):
        from biz_aid_pipeline.config.settings import PipelineError
        retriever, provider = FakeRetriever(RESULTS), FakeProvider({"answer": "x", "evidence_ids": ["E1"], "insufficient_evidence": False})
        empty = RagService(retriever, provider).answer("보증한도는?", candidate_pblanc_ids=())
        # BOUNDARY: 정형 후보가 없으면 검색·LLM 호출 없이 고정 결과를 돌려준다.
        self.assertEqual((empty.status, empty.candidate_count, retriever.calls, provider.requests), ("NO_CANDIDATES", 0, [], []))
        scoped = RagService(retriever, provider).answer("보증한도는?", candidate_pblanc_ids=("PBLN_1", "PBLN_2"))
        self.assertEqual((retriever.calls[-1], scoped.candidate_count), (("보증한도는?", "hybrid", 5, ("PBLN_1", "PBLN_2")), 2))
        with self.assertRaisesRegex(PipelineError, "retrieval_scope_violation"):
            RagService(FakeRetriever(RESULTS), provider).answer("보증한도는?", candidate_pblanc_ids=("PBLN_1",))


class LangChainProviderTests(unittest.TestCase):
    def test_ollama_provider_sends_schema_through_langchain_and_maps_errors_to_fixed_codes(self):
        from langchain_core.messages import AIMessageChunk
        from biz_aid_pipeline.config.settings import PipelineError
        from biz_aid_pipeline.rag.llm import LlmRequest, OllamaLlmProvider

        class FakeChat:
            """ChatOllama.stream 대역. 응답을 chunk 하나로 흘려보낸다(전체 기한 확인은 chunk 사이에서 한다)."""

            def __init__(self, result):
                self.result, self.calls = result, []

            def stream(self, messages, **kwargs):
                self.calls.append((messages, kwargs))
                if isinstance(self.result, Exception):
                    raise self.result
                yield self.result

        schema = {"type": "object", "properties": {"answer": {"type": "string"}}}
        chat = FakeChat(AIMessageChunk(content='{"answer": "{x}"}', response_metadata={"model": "qwen", "eval_count": 3}))
        provider = OllamaLlmProvider("http://127.0.0.1:11434", "qwen", 5, "1m", chat=chat)
        response = provider.generate(LlmRequest("규칙 {중괄호}", "질문", schema))
        messages, kwargs = chat.calls[0]
        # prompt 본문의 중괄호는 template 변수로 해석되지 않고, 출력 schema는 Ollama format으로 그대로 간다.
        self.assertEqual([message.content for message in messages], ["규칙 {중괄호}", "질문"])
        self.assertEqual((kwargs["format"], kwargs["options"]), (schema, {"temperature": 0.0}))
        self.assertEqual((response.text, response.provider, response.model, response.usage["eval_count"]),
                         ('{"answer": "{x}"}', "ollama", "qwen", 3))
        failure = OSError("connect to 127.0.0.1 failed")
        with self.assertRaisesRegex(PipelineError, "^llm_unavailable$"):
            OllamaLlmProvider("u", "m", 5, "1m", chat=FakeChat(failure)).generate(LlmRequest("s", "u", schema))
        http_error = RuntimeError("bad")
        http_error.status_code = 500
        with self.assertRaisesRegex(PipelineError, "^llm_http_error:500$"):
            OllamaLlmProvider("u", "m", 5, "1m", chat=FakeChat(http_error)).generate(LlmRequest("s", "u", schema))

    def test_total_deadline_closes_the_stream_and_limits_are_sent_in_options(self):
        from langchain_core.messages import AIMessageChunk
        from biz_aid_pipeline.config.settings import PipelineError
        from biz_aid_pipeline.rag.llm import LlmRequest, OllamaLlmProvider, llm_call_limits, provider_from_settings

        class EndlessChat:
            """token을 끝없이 보내는 생성(반복 폭주). 연결을 닫았는지 기록한다."""

            def __init__(self):
                self.closed, self.kwargs = False, None

            def stream(self, messages, **kwargs):
                self.kwargs = kwargs
                try:
                    while True:
                        yield AIMessageChunk(content='{"criterion":"같은 조건",')
                except GeneratorExit:
                    self.closed = True
                    raise

        chat = EndlessChat()
        provider = OllamaLlmProvider("u", "m", 0.05, "1m", chat=chat, num_ctx=32768)
        with self.assertRaisesRegex(PipelineError, "^llm_timeout$"):
            provider.generate(LlmRequest("s", "u", {"type": "object"}, max_output_tokens=1024))
        # 기한이 지나면 stream을 닫는다(실제 Ollama는 연결이 닫히면 생성을 멈춘다). 상한은 options로 같이 간다.
        self.assertTrue(chat.closed)
        self.assertEqual(chat.kwargs["options"], {"temperature": 0.0, "num_ctx": 32768, "num_predict": 1024})
        # 읽기 대기 시간 초과 예외도 같은 고정 코드다.
        class ReadTimeout(Exception):
            pass
        class SlowChat:
            def stream(self, messages, **kwargs):
                raise ReadTimeout("no first token")
                yield
        with self.assertRaisesRegex(PipelineError, "^llm_timeout$"):
            OllamaLlmProvider("u", "m", 5, "1m", chat=SlowChat()).generate(LlmRequest("s", "u", {}))
        # 설정은 기한을 줄일 수만 있고 Spring 응답 제한(90초)보다 짧은 계약값을 넘지 못한다.
        deadline, context = llm_call_limits()
        self.assertLess(deadline, 90)
        self.assertEqual(context, 32768)
        # 설정 파일 없이 process environment만으로 확인한다(.env.dev를 읽지 않도록 없는 root를 준다).
        environ = {"OLLAMA_MODEL": "qwen", "OLLAMA_TIMEOUT_SECONDS": "300"}
        self.assertEqual(provider_from_settings("dev", ROOT / "missing-root-for-env", environ).timeout_seconds, deadline)
        self.assertEqual(provider_from_settings("dev", ROOT / "missing-root-for-env",
                                                dict(environ, OLLAMA_TIMEOUT_SECONDS="30")).timeout_seconds, 30)
        self.assertEqual(provider_from_settings("dev", ROOT / "missing-root-for-env", {"OLLAMA_MODEL": "qwen"}).num_ctx, context)


if __name__ == "__main__":
    unittest.main()
