import ast
import sys
import unittest
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data-pipeline/src"))

from qdrant_client import QdrantClient

from biz_aid_pipeline.chunking.chunker import chunk_document
from biz_aid_pipeline.config.settings import PipelineError
from biz_aid_pipeline.indexing import qdrant_store
from biz_aid_pipeline.indexing.embedder import indexing_contract
from biz_aid_pipeline.indexing.pipeline import index_chunks
from biz_aid_pipeline.retrieval.retriever import PAYLOAD_FIELDS, Retriever, rrf
from test_document_chunking import SOURCE, sample_document
from test_document_indexing import FakeEmbedder, identity

RETRIEVAL = ROOT / "data-pipeline/src/biz_aid_pipeline/retrieval"
# 적재·변환·collection 변경 경로. Retriever가 부르면 read-only 경계가 깨진다.
WRITE_CALLS = {"upsert", "delete", "delete_stale", "delete_collection", "create_collection", "recreate_collection",
               "create_payload_index", "ensure_collection", "set_payload", "overwrite_payload", "update_vectors",
               "index_source", "index_chunks", "chunk_source", "chunk_document", "parse_document", "load_chunk_source"}


class CharEmbedder(FakeEmbedder):
    """sparse를 글자 단위로 만들어 query와 문서가 겹치게 한다. dense는 FakeEmbedder와 같다."""

    def encode(self, texts):
        dense = super().encode(texts)
        return [(vector, {"indices": sorted({ord(ch) for ch in text if not ch.isspace()}),
                          "values": [1.0] * len({ord(ch) for ch in text if not ch.isspace()})})
                for (vector, _), text in zip(dense, texts)]


class DocumentRetrievalContractTests(unittest.TestCase):
    def test_retriever_reads_only_the_embedding_identity_collection(self):
        contract = indexing_contract()
        client = QdrantClient(":memory:")
        embedder = CharEmbedder(identity(), contract["qdrant"]["vectors"]["dense"]["size"])
        chunks = chunk_document(sample_document(), SOURCE)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            index_chunks(chunks, SOURCE.source_sha256, embedder, client, contract)
        retriever = Retriever(embedder, client, contract)
        self.assertEqual(retriever.collection, qdrant_store.collection_name(contract, embedder.identity["embedding_key"]))
        before = (client.count(retriever.collection, exact=True).count, [c.name for c in client.get_collections().collections])
        by_id = {chunk.chunk_id: chunk.payload() for chunk in chunks}
        for mode in ("dense", "sparse", "hybrid"):
            results = retriever.search("업력 3년 이하", mode, top_k=3)
            self.assertTrue(results, mode)
            self.assertEqual([r.rank for r in results], list(range(1, len(results) + 1)))
            self.assertLessEqual(len(results), 3)
            for result in results:
                # 근거 field는 저장된 FinalChunk payload에서 그대로 온다.
                self.assertEqual({name: getattr(result, name) for name in PAYLOAD_FIELDS if name != "embedding_key"},
                                 {name: by_id[result.chunk_id][name] for name in PAYLOAD_FIELDS if name != "embedding_key"})
        hybrid = retriever.search("업력 3년 이하", "hybrid", top_k=3)
        self.assertEqual([r.chunk_id for r in hybrid], [r.chunk_id for r in retriever.search("업력 3년 이하", "hybrid", top_k=3)])
        self.assertTrue(all(r.rrf_score is not None and (r.dense_rank or r.sparse_rank) for r in hybrid))
        filtered = retriever.search("업력 3년 이하", "dense", top_k=5, pblanc_id="PBLN_2")
        self.assertEqual({r.pblanc_id for r in filtered}, {"PBLN_2"})
        self.assertEqual((client.count(retriever.collection, exact=True).count,
                          [c.name for c in client.get_collections().collections]), before)
        # 다른 embedding identity는 다른 collection을 가리키며, 없으면 만들지 않고 실패한다.
        with self.assertRaisesRegex(PipelineError, "retrieval_collection_missing"):
            Retriever(FakeEmbedder(identity("f" * 64), 1024), client, contract)
        self.assertEqual([c.name for c in client.get_collections().collections], before[1])

    def test_rrf_uses_ranks_only_and_breaks_ties_deterministically(self):
        # a는 두 목록 1·2위, b는 2·1위라 점수가 같다. 최고 순위도 같아 point id 순서로 정한다.
        fused = rrf([["a", "b", "c"], ["b", "a", "d"]], 60, 4)
        self.assertEqual([point_id for point_id, _ in fused], ["a", "b", "c", "d"])
        self.assertAlmostEqual(fused[0][1], 1 / 61 + 1 / 62)
        self.assertEqual(fused, rrf([["a", "b", "c"], ["b", "a", "d"]], 60, 4))
        # 한 목록에만 있는 1위(e)는 두 목록 모두 3위인 f보다 낮다. 점수 척도는 쓰지 않는다.
        self.assertEqual([p for p, _ in rrf([["e", "x", "f"], ["y", "z", "f"]], 60, 5)][:2], ["f", "e"])

    def test_retrieval_code_is_read_only_and_reuses_indexing_embedder(self):
        for path in RETRIEVAL.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            called = {node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", None)
                      for node in ast.walk(tree) if isinstance(node, ast.Call)}
            self.assertFalse(called & WRITE_CALLS, path.name)
            imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
            imported |= {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
            # BOUNDARY: 별도 query 모델·tokenizer를 두지 않고 indexing의 BgeM3Embedder만 쓴다. 적재 단계 module도 import하지 않는다.
            self.assertFalse({name for name in imported if name and name.split(".")[0] in {"torch", "transformers", "FlagEmbedding"}}, path.name)
            self.assertFalse({name for name in imported if name and name.startswith(
                ("biz_aid_pipeline.parsing", "biz_aid_pipeline.chunking", "biz_aid_pipeline.indexing.pipeline"))}, path.name)

    def test_evaluation_refuses_changed_gold_and_judges_source_and_evidence(self):
        import hashlib
        import json
        import tempfile
        sys.path.insert(0, str(ROOT))
        from evals.retrieval.evaluate import judge, load_frozen_gold
        item = {"expected_source_sha256": "s1", "expected_evidence": [{"chunk_id": "c2"}, {"chunk_id": "c3"}]}
        results = [{"source_sha256": "s1", "chunk_id": "c1"}, {"source_sha256": "s2", "chunk_id": "x"},
                   {"source_sha256": "s1", "chunk_id": "c3"}]
        self.assertEqual(judge(item, results), {"source_hit_at_1": True, "source_hit_at_5": True, "evidence_hit_at_5": True,
                                                "evidence_rank": 3})
        self.assertFalse(judge(item, results[1:2])["source_hit_at_1"])
        with tempfile.TemporaryDirectory() as directory:
            raw = b'{"items": []}\n'
            Path(directory, "gold.json").write_bytes(raw)
            Path(directory, "gold.frozen.json").write_text(json.dumps({"sha256": hashlib.sha256(raw).hexdigest()}))
            load_frozen_gold(directory)
            # BOUNDARY: 결과를 본 뒤 Gold를 고치면 동결 hash와 달라 평가를 거부한다.
            Path(directory, "gold.json").write_bytes(b'{"items": [1]}\n')
            with self.assertRaises(SystemExit):
                load_frozen_gold(directory)


if __name__ == "__main__":
    unittest.main()
