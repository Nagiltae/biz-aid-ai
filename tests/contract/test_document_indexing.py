import copy
import dataclasses
import sys
import unittest
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data-pipeline/src"))

from qdrant_client import QdrantClient, models

from biz_aid_pipeline.chunking.chunker import chunk_document, chunking_contract
from biz_aid_pipeline.config.settings import PipelineError
from biz_aid_pipeline.indexing import qdrant_store
from biz_aid_pipeline.indexing.embedder import embedding_identity, indexing_contract, sparse_vector
from biz_aid_pipeline.indexing.pipeline import index_chunks
from biz_aid_pipeline.parsing.models import artifact_files, parsing_contract, scoped_artifacts_sha256
from test_document_chunking import SOURCE, sample_document


class FakeEmbedder:
    """모델 없이 저장 경로를 검증한다. vector는 text 길이로만 정해져 같은 text면 같다."""

    def __init__(self, identity, dimension):
        self.identity, self.dimension, self.calls = identity, dimension, []

    def encode(self, texts):
        self.calls.append(len(texts))
        return [([1.0] + [0.0] * (self.dimension - 1), {"indices": [len(text)], "values": [0.5]}) for text in texts]


def identity(key="e" * 64):
    handoff = chunking_contract()["embedding_handoff"]
    return {"model_repo_id": handoff["model_repo_id"], "model_revision": handoff["model_revision"], "embedding_key": key}


class DocumentIndexingContractTests(unittest.TestCase):
    def test_embedding_model_aligns_with_chunking_tokenizer_and_identity_is_scoped(self):
        contract, chunking, parse_contract = indexing_contract(), chunking_contract(), parsing_contract()
        spec = contract["embedding"]
        self.assertEqual((spec["model_repo_id"], spec["model_revision"]),
                         (chunking["tokenizer"]["repo_id"], chunking["tokenizer"]["revision"]))
        self.assertEqual(spec["tokenizer_artifact_folder"], chunking["tokenizer"]["artifact_folder"])
        model = next(m for m in parse_contract["dependencies"]["docling"]["model_artifacts"]["models"]
                     if m["folder"] == spec["weights_artifact_folder"])
        self.assertEqual((model["repo_id"], model["resolved_snapshot"], model["scope"]),
                         (spec["model_repo_id"], spec["model_revision"], spec["weights_artifact_scope"]))
        # BOUNDARY: embedding 가중치를 같은 artifact 체계에 두어도 parse_key·chunk identity 계산 파일에는 들어가지 않는다.
        for scope in ("parsing", "chunking"):
            self.assertNotIn(spec["weights_artifact_folder"], {folder for folder, _ in artifact_files(parse_contract, scope)})
        self.assertNotEqual(scoped_artifacts_sha256(parse_contract, "embedding"), scoped_artifacts_sha256(parse_contract, "chunking"))
        base = embedding_identity(contract, parse_contract)["embedding_key"]
        for mutate in (lambda c: c["embedding"].update(model_revision="0" * 40), lambda c: c["embedding"].update(embedding_version=2),
                       lambda c: c["embedding"]["dense"].update(normalize="none")):
            other = copy.deepcopy(contract)
            mutate(other)
            self.assertNotEqual(base, embedding_identity(other, parse_contract)["embedding_key"])
        self.assertEqual(base, embedding_identity(indexing_contract(), parse_contract)["embedding_key"])

    def test_sparse_vector_keeps_max_positive_weight_per_token_and_drops_special_and_padding(self):
        # token 0=cls, 2=eos, 1=pad. 같은 token 7은 최댓값만 남고 0 이하 weight는 빠진다.
        result = sparse_vector([0, 7, 9, 7, 5, 2, 1], [0.9, 0.2, 0.0, 0.4, -0.1, 0.8, 0.7], [1, 1, 1, 1, 1, 1, 0], {0, 1, 2, 3})
        self.assertEqual(result, {"indices": [7], "values": [0.4]})

    def test_points_keep_chunk_identity_rerun_is_idempotent_and_stale_points_are_removed(self):
        contract = indexing_contract()
        dimension = contract["qdrant"]["vectors"]["dense"]["size"]
        embedder = FakeEmbedder(identity(), dimension)
        client = QdrantClient(":memory:")
        chunks = chunk_document(sample_document(), SOURCE)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            first = index_chunks(chunks, SOURCE.source_sha256, embedder, client, contract)
            second = index_chunks(chunks, SOURCE.source_sha256, embedder, client, contract)
        name = first["collection"]
        self.assertTrue(first["collection_created"])
        self.assertFalse(second["collection_created"])
        # 공고 두 개가 content_key를 공유하므로 embedding은 content 수만큼만 계산한다.
        self.assertEqual(first["embedded"], len({chunk.content_key for chunk in chunks}))
        self.assertLess(first["embedded"], len(chunks))
        self.assertEqual(client.count(name, exact=True).count, len(chunks))
        stored = client.retrieve(name, [chunks[0].chunk_id], with_payload=True)[0]
        self.assertEqual(str(stored.id), chunks[0].chunk_id)
        self.assertEqual(stored.payload, dict(chunks[0].payload(), embedding_key=embedder.identity["embedding_key"]))
        # 다시 chunking돼 chunk 집합이 바뀌면 같은 source의 이전 point는 남지 않는다.
        rechunked = [dataclasses.replace(chunk, chunk_id="00000000-0000-5000-8000-%012d" % index)
                     for index, chunk in enumerate(chunks[:2])]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            third = index_chunks(rechunked, SOURCE.source_sha256, embedder, client, contract)
        self.assertEqual((third["stale_deleted"], third["source_points"]), (len(chunks), 2))

    def test_incompatible_collection_or_model_fails_without_changing_the_collection(self):
        contract = indexing_contract()
        client = QdrantClient(":memory:")
        name = qdrant_store.collection_name(contract, identity()["embedding_key"])
        client.create_collection(name, vectors_config={"dense": models.VectorParams(size=8, distance=models.Distance.DOT)})
        chunks = chunk_document(sample_document(), SOURCE)
        with self.assertRaisesRegex(PipelineError, "qdrant_collection_schema_mismatch"):
            index_chunks(chunks, SOURCE.source_sha256, FakeEmbedder(identity(), 8), client, contract)
        self.assertEqual(client.get_collection(name).config.params.vectors["dense"].size, 8)
        other_model = dict(identity(), model_revision="0" * 40)
        with self.assertRaisesRegex(PipelineError, "chunk_embedding_model_mismatch"):
            index_chunks(chunks, SOURCE.source_sha256, FakeEmbedder(other_model, 8), client, contract)
        with self.assertRaisesRegex(PipelineError, "qdrant_url_not_loopback"):
            qdrant_store.qdrant_url("dev", environ={"QDRANT_URL": "http://10.0.0.5:6333"})

    def test_bounded_indexing_runner_processes_only_targets_resumes_and_isolates_failures(self):
        from biz_aid_pipeline.indexing.corpus import drive
        calls, written = [], []

        def index_one(sha):
            calls.append(sha)
            if sha == "c":
                raise PipelineError("current_parsed_artifact_required")
            return {"source_sha256": sha, "status": "INDEXED", "chunks": 2, "collection": "bizaid_chunks_v1_x"}
        state = {"run_id": "r", "state": "RUNNING", "stop_reason": None, "total": 4, "completed": 0, "indexed": 0, "failed": 0,
                 "skipped": 0, "current": None, "chunks": 0, "failures": {}, "processed_seconds": 0.0, "collection": None,
                 "started": 0.0, "source_points": {}}
        drive(["a", "b", "c", "d"], index_one, {"b"}, state, lambda outcome, _: written.append(outcome))
        # 목록 밖 source는 없고, 이미 INDEXED인 b는 다시 처리하지 않으며, c 실패 뒤에도 d를 처리한다.
        self.assertEqual(calls, ["a", "c", "d"])
        self.assertEqual((state["state"], state["completed"], state["indexed"], state["failed"], state["skipped"], state["chunks"]),
                         ("COMPLETED", 4, 2, 1, 1, 4))
        self.assertEqual(state["failures"], {"current_parsed_artifact_required": 1})
        stopped = dict(state, state="RUNNING", completed=0)
        drive(["a"], index_one, set(), stopped, lambda *_: None, lambda: True)
        self.assertEqual(stopped["state"], "STOPPED_SIGNAL")


if __name__ == "__main__":
    unittest.main()
