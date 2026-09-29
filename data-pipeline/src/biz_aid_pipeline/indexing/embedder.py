"""BAAI/bge-m3 dense + sparse embedding. 고정 artifact에서만 적재하고 batch로 추론한다.

dense는 CLS hidden state의 L2 정규화, sparse는 sparse_linear의 token별 ReLU weight를 token id별 최댓값으로 모은 것이다(BGE-M3 출력 정의).
"""
import hashlib
import json
from functools import lru_cache

from biz_aid_pipeline.config.settings import ROOT, PipelineError, read_json
from biz_aid_pipeline.parsing.models import docling_artifacts_path, installed_version, parsing_contract, scoped_artifacts_sha256

CONTRACT_PATH = ROOT / "contracts/schemas/document-indexing.contract.json"


def indexing_contract(path=CONTRACT_PATH):
    return read_json(path)


def canonical_sha256(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def embedding_identity(contract, parse_contract=None):
    """embedding 결과에 영향을 주는 모델·artifact·설정·runtime 버전. 바뀌면 새 embedding_key와 새 collection이다."""
    parse_contract = parse_contract or parsing_contract()
    spec = contract["embedding"]
    identity = {"model_repo_id": spec["model_repo_id"], "model_revision": spec["model_revision"],
                "embedding_version": spec["embedding_version"], "embedding_config_sha256": canonical_sha256(spec),
                "embedding_artifacts_sha256": scoped_artifacts_sha256(parse_contract, spec["weights_artifact_scope"]),
                "tokenizer_artifacts_sha256": scoped_artifacts_sha256(parse_contract, "chunking"),
                "torch_version": installed_version("torch"), "transformers_version": installed_version("transformers")}
    selected = {name: identity[name] for name in contract["identity"]["embedding_key_inputs"]}
    return dict(selected, embedding_key=canonical_sha256(selected))


def sparse_vector(token_ids, weights, mask, excluded):
    """token별 weight를 token id별 최댓값으로 모은다. padding·특수 token·0 이하 weight는 넣지 않는다."""
    sparse = {}
    for token_id, weight, used in zip(token_ids, weights, mask):
        if used and token_id not in excluded and weight > 0:
            sparse[token_id] = max(weight, sparse.get(token_id, 0.0))
    indices = sorted(sparse)
    return {"indices": indices, "values": [sparse[index] for index in indices]}


@lru_cache(maxsize=1)
def _model(weights_path, tokenizer_path, dtype):
    import torch
    from transformers import AutoModel, AutoTokenizer
    # BOUNDARY: Hub에 접속하지 않고 고정 artifact만 읽는다. 파일이 없으면 여기서 실패한다.
    tokenizer = AutoTokenizer.from_pretrained(tokenizer_path, local_files_only=True)
    model = AutoModel.from_pretrained(weights_path, local_files_only=True, dtype=getattr(torch, dtype))
    model.eval()
    sparse = torch.nn.Linear(model.config.hidden_size, 1)
    sparse.load_state_dict(torch.load(f"{weights_path}/sparse_linear.pt", map_location="cpu", weights_only=True))
    sparse.eval()
    return tokenizer, model, sparse


class BgeM3Embedder:
    def __init__(self, contract=None, parse_contract=None):
        self.contract = contract or indexing_contract()
        parse_contract = parse_contract or parsing_contract()
        spec = self.contract["embedding"]
        self.identity = embedding_identity(self.contract, parse_contract)
        root = docling_artifacts_path(parse_contract)
        self.spec = spec
        self.tokenizer, self.model, self.sparse = _model(str(root / spec["weights_artifact_folder"]),
                                                         str(root / spec["tokenizer_artifact_folder"]), spec["dtype"])
        excluded = {"cls": self.tokenizer.cls_token_id, "eos": self.tokenizer.eos_token_id,
                    "pad": self.tokenizer.pad_token_id, "unk": self.tokenizer.unk_token_id}
        self.excluded = {excluded[name] for name in spec["sparse"]["excluded_tokens"]}

    def encode(self, texts):
        """text 목록을 batch_size 단위로 추론해 (dense, sparse) 목록을 같은 순서로 돌려준다."""
        import torch
        results = []
        size = self.spec["batch_size"]
        for start in range(0, len(texts), size):
            batch = texts[start:start + size]
            encoded = self.tokenizer(batch, padding=True, truncation=False, return_tensors="pt")
            # BOUNDARY: 잘라서 embedding하면 chunk text 일부가 검색에서 사라진다. 한도를 넘으면 실패시킨다.
            if encoded["input_ids"].shape[1] > self.spec["max_length"]:
                raise PipelineError("embedding_input_exceeds_max_length")
            with torch.no_grad():
                hidden = self.model(**encoded).last_hidden_state
                dense = torch.nn.functional.normalize(hidden[:, 0], p=2, dim=-1)
                weights = torch.relu(self.sparse(hidden)).squeeze(-1)
            for row in range(len(batch)):
                results.append((dense[row].tolist(), sparse_vector(encoded["input_ids"][row].tolist(), weights[row].tolist(),
                                                                   encoded["attention_mask"][row].tolist(), self.excluded)))
        return results
