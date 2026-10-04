import copy
import hashlib
import importlib.metadata
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data-pipeline/src"))

from biz_aid_pipeline.config.settings import PipelineError
from biz_aid_pipeline.indexing.qdrant_store import qdrant_url
from biz_aid_pipeline.parsing.models import (artifacts_manifest_sha256, docling_artifacts_path, parsing_contract,
                                             verified_scope_artifacts_sha256)

API_REQUIREMENTS = ROOT / "data-pipeline/requirements-api.txt"
PIPELINE_REQUIREMENTS = ROOT / "data-pipeline/requirements.txt"
# 파싱 전용 의존성. 질문 처리 이미지에 들어가면 이미지가 수 GB로 커지고 파싱 경계가 섞인다.
PARSING_ONLY = ("docling-slim", "docling-ibm-models", "paddlepaddle", "paddlex", "opencv-python-headless",
                "python-docx", "python-pptx", "xlsxwriter", "defusedxml")


def requirement_lines(path):
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip() and not line.startswith("#")]


def package(line):
    return re.split(r"[\[=<>]", line, maxsplit=1)[0].lower()


class QdrantAddressTests(unittest.TestCase):
    def test_loopback_and_compose_service_only(self):
        for url in ("http://127.0.0.1:6333", "http://localhost:6333", "http://qdrant:6333", "http://qdrant:6333/"):
            self.assertEqual(qdrant_url("dev", ROOT, {"QDRANT_URL": url}).rstrip("/"), url.rstrip("/"))
        # 2026-10-03 결정으로 compose 서비스 이름 하나만 더 허용한다. 다른 포트·https·다른 이름·원격 주소는 거부한다.
        for url in ("http://qdrant:6334", "https://qdrant:6333", "http://qdrant.example.com:6333", "http://10.0.0.5:6333",
                    "http://qdrant-other:6333"):
            with self.subTest(url=url), self.assertRaises(PipelineError):
                qdrant_url("dev", ROOT, {"QDRANT_URL": url})


class ScopedArtifactTests(unittest.TestCase):
    def fake_artifacts(self, directory, with_parsing):
        """합성 artifact: parsing 1개·chunking 1개·embedding 1개 모델. 계약의 단계별 기대값을 이 파일로 다시 계산한다."""
        contract = copy.deepcopy(parsing_contract())
        spec = contract["dependencies"]["docling"]["model_artifacts"]
        spec["models"] = [{"folder": "parse-model", "files": ["w.bin"]},
                          {"folder": "tokenizer", "files": ["t.json"], "scope": "chunking"},
                          {"folder": "weights", "files": ["m.bin"], "scope": "embedding"}]
        for folder, name in (("tokenizer", "t.json"), ("weights", "m.bin")) + ((("parse-model", "w.bin"),) if with_parsing else ()):
            (directory / folder).mkdir(parents=True, exist_ok=True)
            (directory / folder / name).write_bytes(hashlib.sha256((folder + name).encode()).digest())
        for scope, files in (("chunking", (("tokenizer", "t.json"),)), ("embedding", (("weights", "m.bin"),))):
            spec["expected_scope_manifest_sha256"][scope] = artifacts_manifest_sha256(str(directory), files)
        return contract, {spec["artifacts_path_env"]: str(directory)}

    def test_query_server_needs_only_bge_scope_files(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            contract, environ = self.fake_artifacts(directory, with_parsing=False)
            # 파싱 모델이 없어도 BGE-M3 범위(tokenizer·가중치)만 있으면 검증되고 같은 단계별 manifest를 돌려준다.
            for scope in ("chunking", "embedding"):
                self.assertEqual(verified_scope_artifacts_sha256(contract, scope, environ),
                                 contract["dependencies"]["docling"]["model_artifacts"]["expected_scope_manifest_sha256"][scope])
            self.assertEqual(docling_artifacts_path(contract, environ, ("chunking", "embedding")), directory.resolve())
            # 파싱 쪽(전체 목록) 검증은 그대로라 파싱 모델이 없으면 실패한다.
            with self.assertRaises(PipelineError):
                docling_artifacts_path(contract, environ)
            # 가중치 내용이 바뀌면 단계별 기대값과 달라 실패한다(가짜 가중치로 같은 embedding_key를 만들지 않음).
            (directory / "weights" / "m.bin").write_bytes(b"other weights")
            artifacts_manifest_sha256.cache_clear()
            with self.assertRaisesRegex(PipelineError, "docling_artifacts_scope_identity_mismatch:embedding"):
                verified_scope_artifacts_sha256(contract, "embedding", environ)

    @unittest.skipUnless(os.environ.get("BIZAID_DOCLING_ARTIFACTS_PATH"), "real model artifacts required")
    def test_scope_only_embedding_key_equals_full_verification(self):
        from biz_aid_pipeline.indexing.embedder import embedding_identity, indexing_contract
        contract = indexing_contract()
        # BOUNDARY: 질문 서버의 검증 방식만 바뀌고 embedding_key(=검색 collection 이름)는 같아야 한다.
        self.assertEqual(embedding_identity(contract, scope_only=True), embedding_identity(contract))


class RuntimeVersionTests(unittest.TestCase):
    def test_cpu_build_label_does_not_change_embedding_runtime_version(self):
        from biz_aid_pipeline.indexing.embedder import public_version
        self.assertEqual(public_version("2.14.0+cpu"), "2.14.0")
        self.assertEqual(public_version("2.14.0"), "2.14.0")
        self.assertIsNone(public_version(None))
        # 다른 공개 버전은 그대로 다르다(버전이 바뀌면 새 embedding_key라는 규칙은 유지).
        self.assertNotEqual(public_version("2.15.0+cpu"), public_version("2.14.0"))


class RequirementSplitTests(unittest.TestCase):
    def test_api_requirements_are_pinned_subset_without_parsing_dependencies(self):
        api = requirement_lines(API_REQUIREMENTS)
        pipeline = requirement_lines(PIPELINE_REQUIREMENTS)
        self.assertTrue(all("==" in line for line in api))
        self.assertEqual(pipeline[0], "-r requirements-api.txt")
        self.assertFalse({package(line) for line in api} & set(PARSING_ONLY))
        for name in ("fastapi", "uvicorn", "qdrant-client", "langchain-core", "langchain-ollama", "langgraph", "langsmith",
                     "sqlalchemy", "pymysql", "torch", "transformers", "boto3", "jsonschema"):
            self.assertIn(name, {package(line) for line in api})
        # 파이프라인 파일에 같은 패키지를 다른 버전으로 다시 적지 않는다(extra만 더할 수 있다).
        versions = {package(line): line.split("==")[1] for line in api}
        for line in pipeline[1:]:
            if package(line) in versions:
                self.assertEqual(line.split("==")[1], versions[package(line)], line)

    def test_embedding_runtime_versions_match_the_pipeline_environment(self):
        # WHY: torch·transformers 버전은 embedding_key 입력이다. 이미지와 host가 다르면 질문 서버가 다른 collection을 찾는다.
        pinned = {package(line): line.split("==")[1] for line in requirement_lines(API_REQUIREMENTS)}
        for name in ("torch", "transformers"):
            try:
                installed = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:
                self.skipTest(name + " not installed")
            self.assertEqual(pinned[name], installed)


class ContainerFilesTests(unittest.TestCase):
    def test_dockerfile_and_dev_script_boundaries(self):
        dockerfile = (ROOT / "data-pipeline/Dockerfile").read_text(encoding="utf-8")
        self.assertIn("COPY requirements-api.txt", dockerfile)
        self.assertNotIn("requirements.txt /", dockerfile.replace("requirements-api.txt", ""))
        # 코드·모델을 이미지에 복사하지 않는다(코드는 mount, 모델은 host artifact).
        self.assertNotRegex(dockerfile, r"COPY\s+(src|\.)\s")
        self.assertIn("USER bizaid", dockerfile)
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn("${HOME}/.aws:/home/bizaid/.aws:ro", compose)
        self.assertIn("AWS_PROFILE: ${AWS_PROFILE:-}", compose)
        self.assertNotIn("AWS_ACCESS_KEY_ID:", compose)
        self.assertNotIn("AWS_SECRET_ACCESS_KEY:", compose)
        dev = (ROOT / "scripts/dev.sh").read_text(encoding="utf-8")
        self.assertIn('docker compose --env-file "$ROOT/.env.dev" --profile app', dev)
        # 데이터 volume을 지우는 명령과 설정 값 출력은 두지 않는다.
        self.assertNotRegex(dev, r"down\s+(-v|--volumes)")
        self.assertNotIn("compose config", dev)
        # profile 없는 phase0 도구는 개발 환경과 함께 올리지 않는다.
        self.assertIn('SERVICES="mysql qdrant fastapi backend frontend"', dev)
        self.assertIn("compose up -d $SERVICES", dev)
        self.assertNotRegex(dev, r"cat\s+[\"$A-Za-z/]*\.env")


if __name__ == "__main__":
    unittest.main()
