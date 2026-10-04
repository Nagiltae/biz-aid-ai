import io
import json
import time
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import Mock, patch

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data-pipeline/src"))

from biz_aid_pipeline.rag.llm import BedrockLlmProvider, LlmRequest, provider_from_settings
from biz_aid_pipeline.config.settings import ROOT, PipelineError
from biz_aid_pipeline.api.app import status_for

SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"], "additionalProperties": False}


class Stream:
    def __init__(self, value='{"answer":"정상"}', stop="tool_use", output=10, delay=0):
        self.value, self.stop, self.output, self.delay, self.closed = value, stop, output, delay, False

    def __iter__(self):
        yield {"contentBlockStart": {"contentBlockIndex": 0, "start": {"toolUse": {"name": "emit_result", "toolUseId": "fixture"}}}}
        if self.delay:
            time.sleep(self.delay)
        yield {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"toolUse": {"input": self.value}}}}
        yield {"messageStop": {"stopReason": self.stop}}
        yield {"metadata": {"usage": {"inputTokens": 100, "outputTokens": self.output}}}

    def close(self):
        self.closed = True


class BedrockTests(unittest.TestCase):
    def provider(self, stream):
        client = Mock()
        client.converse_stream.return_value = {"stream": stream}
        return BedrockLlmProvider(client=client), client

    def test_tool_json_schema_usage_and_identity(self):
        stream = Stream()
        provider, client = self.provider(stream)
        response = provider.generate(LlmRequest("system", "user", SCHEMA, max_output_tokens=100))
        self.assertEqual(json.loads(response.text), {"answer": "정상"})
        self.assertEqual(response.usage["input_tokens"], 100)
        self.assertEqual(response.usage["output_tokens"], 10)
        parameters = client.converse_stream.call_args.kwargs
        self.assertEqual(parameters["toolConfig"]["tools"][0]["toolSpec"]["inputSchema"]["json"], SCHEMA)
        self.assertEqual(parameters["toolConfig"]["toolChoice"], {"tool": {"name": "emit_result"}})
        self.assertEqual(parameters["inferenceConfig"]["maxTokens"], 100)
        self.assertTrue(stream.closed)
        client.converse_stream.assert_called_once()

    def test_invalid_schema_partial_output_and_token_limit_are_fail_closed(self):
        for stream, code in ((Stream('not-json'), "llm_output_schema_mismatch"),
                             (Stream('{"answer":1}'), "llm_output_schema_mismatch"),
                             (Stream(stop="end_turn"), "llm_output_schema_mismatch"),
                             (Stream(stop="max_tokens"), "llm_output_limit_reached"),
                             (Stream(output=100), "llm_output_limit_reached")):
            with self.subTest(code=code), self.assertRaisesRegex(PipelineError, code):
                provider, _ = self.provider(stream)
                provider.generate(LlmRequest("s", "u", SCHEMA, max_output_tokens=100))
            self.assertTrue(stream.closed)
        self.assertEqual(status_for("llm_output_limit_reached"), 502)

    def test_stream_and_first_response_have_a_total_deadline(self):
        stream = Stream(delay=.1)
        provider, client = self.provider(stream)
        provider.timeout_seconds = .02
        started = time.monotonic()
        with self.assertRaisesRegex(PipelineError, "llm_timeout"):
            provider.generate(LlmRequest("s", "u", SCHEMA))
        self.assertLess(time.monotonic() - started, .09)
        self.assertTrue(stream.closed)
        def slow_response(**kwargs):
            time.sleep(.1)
            return {"stream": Stream()}
        client.converse_stream.side_effect = slow_response
        with self.assertRaisesRegex(PipelineError, "llm_timeout"):
            provider.generate(LlmRequest("s", "u", SCHEMA))
        self.assertEqual(status_for("llm_timeout"), 503)

    def test_permission_error_fixed_code_no_reflection_or_retry(self):
        from botocore.exceptions import ClientError
        provider, client = self.provider(Stream())
        client.converse_stream.side_effect = ClientError({"Error": {"Code": "AccessDeniedException", "Message": "fixture-secret-do-not-reflect"}}, "ConverseStream")
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(out), self.assertLogs("biz_aid_pipeline.rag.llm", level="WARNING") as logs:
            with self.assertRaisesRegex(PipelineError, "llm_provider_unavailable"):
                provider.generate(LlmRequest("s", "u", SCHEMA))
        self.assertNotIn("fixture-secret-do-not-reflect", out.getvalue() + str(logs.output))
        client.converse_stream.assert_called_once()
        self.assertEqual(status_for("llm_provider_unavailable"), 503)

    def test_setting_selection_sdk_chain_and_trace_safe_metadata(self):
        provider = provider_from_settings("dev", ROOT, {"LLM_PROVIDER": "bedrock", "AWS_PROFILE": "bizaid-dev"})
        self.assertEqual(provider.aws_profile, "bizaid-dev")
        with patch("boto3.Session") as session:
            provider._client()
            self.assertEqual(session.call_args.kwargs, {"profile_name": "bizaid-dev"})
            self.assertEqual(session.return_value.client.call_args.kwargs["config"].retries["total_max_attempts"], 1)
        span = Mock()
        with patch("biz_aid_pipeline.observability.tracing.step") as step:
            step.return_value.__enter__.return_value = span
            fake, _ = self.provider(Stream())
            fake.generate(LlmRequest("private system", "private profile", SCHEMA))
        self.assertNotIn("private", str(step.call_args) + str(span.record.call_args))
        self.assertEqual(span.record.call_args.kwargs["input_tokens"], 100)
        with self.assertRaisesRegex(PipelineError, "rag_requires_dev_profile"):
            provider_from_settings("prod", ROOT, {})
