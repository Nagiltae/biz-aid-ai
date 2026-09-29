"""DoclingDocument → Docling HybridChunker(BGE-M3 tokenizer) → BizAidChunkEnricher → FinalChunk[].

parser가 만든 canonical DoclingDocument를 그대로 받는다. Markdown을 중간 표현으로 쓰지 않고 format별로 분기하지 않는다.
구조 분할은 docling-core HybridChunker가 맡고, 이 module은 설정·tokenizer identity와 BizAid metadata만 붙인다.
"""
import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path

from biz_aid_pipeline.config.settings import ROOT, read_json
from biz_aid_pipeline.parsing.models import docling_artifacts_path, installed_version, parsing_contract, scoped_artifacts_sha256

CONTRACT_PATH = ROOT / "contracts/schemas/document-chunking.contract.json"
# chunk_id UUIDv5 namespace. 바꾸면 모든 chunk_id가 바뀌므로 고정한다.
CHUNK_NAMESPACE = uuid.UUID("5b0f6a52-6d1e-4c2a-9a55-2f1b9b3c7e10")


def chunking_contract(path=CONTRACT_PATH):
    return read_json(path)


def canonical_sha256(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def chunking_config_sha256(contract):
    tokenizer = contract["tokenizer"]
    return canonical_sha256({"chunker": contract["chunker"], "tokenizer": [tokenizer["repo_id"], tokenizer["revision"]]})


def chunker_identity(contract, parse_contract=None):
    """chunk 결과에 영향을 주는 설정·tokenizer·docling-core 버전. parse identity와 같은 방식으로 기록한다."""
    tokenizer = contract["tokenizer"]
    return {"chunker_version": contract["chunker"]["chunker_version"],
            "chunking_config_sha256": chunking_config_sha256(contract),
            "docling_core_version": installed_version("docling-core"),
            "tokenizer_repo_id": tokenizer["repo_id"], "tokenizer_revision": tokenizer["revision"],
            "tokenizer_artifacts_sha256": scoped_artifacts_sha256(parse_contract or parsing_contract(), tokenizer["artifact_scope"]),
            "max_tokens": contract["chunker"]["max_tokens"]}


def chunk_set_key(source_sha256, parse_key, identity, contract):
    inputs = dict(identity, source_sha256=source_sha256, parse_key=parse_key)
    selected = {name: inputs[name] for name in contract["identity"]["chunk_set_key_inputs"]}
    return canonical_sha256(selected)


@lru_cache(maxsize=2)
def _tokenizer(path, max_tokens):
    from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
    from transformers import AutoTokenizer
    # BOUNDARY: tokenizer는 고정 artifact 경로에서만 읽는다. 실행 중 Hub 다운로드를 하지 않는다.
    return HuggingFaceTokenizer(tokenizer=AutoTokenizer.from_pretrained(path, local_files_only=True), max_tokens=max_tokens)


def tokenizer(contract, parse_contract=None):
    parse_contract = parse_contract or parsing_contract()
    scoped_artifacts_sha256(parse_contract, contract["tokenizer"]["artifact_scope"])
    path = docling_artifacts_path(parse_contract) / contract["tokenizer"]["artifact_folder"]
    return _tokenizer(str(path), contract["chunker"]["max_tokens"])


def hybrid_chunker(contract, parse_contract=None):
    from docling_core.transforms.chunker.hierarchical_chunker import ChunkingDocSerializer, ChunkingSerializerProvider
    from docling_core.transforms.chunker.hybrid_chunker import HybridChunker
    from docling_core.transforms.serializer.markdown import MarkdownParams
    from docling_core.types.doc import ImageRefMode
    settings, serializer = contract["chunker"], contract["chunker"]["serializer"]

    class MetaFreeProvider(ChunkingSerializerProvider):
        """docling 기본 chunking serializer에서 item meta 출력만 끈다. meta는 FinalChunk metadata로 따로 옮긴다."""

        def get_serializer(self, doc):
            # WHY: 기본 serializer는 bizaid__* provenance dict를 본문처럼 출력해 embedding text를 오염시킨다(HWPX에서 관찰).
            return ChunkingDocSerializer(doc=doc, params=MarkdownParams(
                image_mode=ImageRefMode.PLACEHOLDER, image_placeholder=serializer["image_placeholder"],
                escape_underscores=serializer["escape_underscores"], escape_html=serializer["escape_html"],
                allowed_meta_names=set(serializer["allowed_meta_names"]), traverse_pictures=serializer["traverse_pictures"]))
    return HybridChunker(tokenizer=tokenizer(contract, parse_contract), serializer_provider=MetaFreeProvider(),
                         merge_peers=settings["merge_peers"], repeat_table_header=settings["repeat_table_header"],
                         omit_header_on_overflow=settings["omit_header_on_overflow"],
                         always_emit_headings=settings["always_emit_headings"])


@dataclass(frozen=True)
class ChunkSource:
    """chunk할 parsed artifact와 그 source가 붙은 공고 relation. 공고마다 FinalChunk를 만든다."""

    source_sha256: str
    source_format: str
    route: str
    parse_key: str
    parser_identity: dict
    announcements: tuple  # (pblanc_id, 공고명) 쌍의 목록


@dataclass
class FinalChunk:
    chunk_id: str
    content_key: str
    chunk_set_key: str
    chunk_index: int
    chunk_count: int
    pblanc_id: str
    title: str | None
    heading_path: list
    text: str
    embedding_text: str
    token_count: int
    exceeds_max_tokens: bool
    heading_only: bool
    item_labels: list
    source_format: str
    source_sha256: str
    route: str
    parse_key: str
    parser_identity: dict
    pages: list
    provenance: list
    chunker_identity: dict
    embedding_model: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)

    def payload(self):
        """vector store payload. embedding 입력 text는 vector 자체로 대체되므로 넣지 않는다."""
        values = self.to_dict()
        values.pop("embedding_text")
        return values


def item_provenance(item, document):
    """chunk에 포함된 DocItem 하나의 위치. parser가 준 page/bbox와 bizaid__* meta만 옮기고 새 위치를 만들지 않는다."""
    entry = {"item_ref": item.self_ref, "label": item.label.value}
    if item.prov:
        prov = item.prov[0]
        box = prov.bbox.to_top_left_origin(page_height=document.pages[prov.page_no].size.height)
        entry.update(page=prov.page_no, bbox_pt=[round(box.l, 2), round(box.t, 2), round(box.r, 2), round(box.b, 2)])
    custom = item.meta.get_custom_part() if getattr(item, "meta", None) else {}
    hwpx = custom.get("bizaid__hwpx")
    if hwpx:
        entry.update(section=hwpx.get("section"), xml_path=hwpx.get("path"))
    table = custom.get("bizaid__table_quality")
    if table:
        entry.update(table_verdict=table.get("verdict"), table_reasons=table.get("reasons"))
    ocr = custom.get("bizaid__ocr")
    if ocr:
        entry.update(ocr_confidence=ocr.get("confidence"))
    return entry


def chunk_document(document, source, contract=None, parse_contract=None):
    """한 DoclingDocument를 HybridChunker로 나누고 공고 relation마다 FinalChunk를 만든다(BizAidChunkEnricher)."""
    contract = contract or chunking_contract()
    parse_contract = parse_contract or parsing_contract()
    if not source.announcements:
        raise ValueError("chunk_source_without_announcement")
    chunker = hybrid_chunker(contract, parse_contract)
    counter = tokenizer(contract, parse_contract)
    identity = chunker_identity(contract, parse_contract)
    set_key = chunk_set_key(source.source_sha256, source.parse_key, identity, contract)
    max_tokens = contract["chunker"]["max_tokens"]
    handoff = contract["embedding_handoff"]
    embedding_model = {"repo_id": handoff["model_repo_id"], "revision": handoff["model_revision"]}
    raw_chunks = list(chunker.chunk(document))
    results = []
    for index, chunk in enumerate(raw_chunks):
        embedding_text = chunker.contextualize(chunk)
        token_count = counter.count_tokens(embedding_text)
        provenance = [item_provenance(item, document) for item in chunk.meta.doc_items]
        pages = sorted({entry["page"] for entry in provenance if "page" in entry})
        content_key = canonical_sha256([set_key, index])
        headings = list(chunk.meta.headings or [])
        # WHY: 본문 없이 이어지는 heading도 버리지 않도록 always_emit_headings로 받은 heading-only chunk는 heading 경로를 text로 둔다.
        heading_only = not chunk.text.strip()
        text = "\n".join(headings) if heading_only else chunk.text
        for pblanc_id, title in source.announcements:
            results.append(FinalChunk(
                chunk_id=str(uuid.uuid5(CHUNK_NAMESPACE, f"{set_key}:{pblanc_id}:{index}")),
                content_key=content_key, chunk_set_key=set_key, chunk_index=index, chunk_count=len(raw_chunks),
                pblanc_id=pblanc_id, title=title, heading_path=headings, text=text,
                embedding_text=embedding_text, token_count=token_count, exceeds_max_tokens=token_count > max_tokens,
                heading_only=heading_only,
                item_labels=sorted({entry["label"] for entry in provenance}), source_format=source.source_format,
                source_sha256=source.source_sha256, route=source.route, parse_key=source.parse_key,
                parser_identity=source.parser_identity, pages=pages, provenance=provenance,
                chunker_identity=dict(identity, chunk_set_key=set_key), embedding_model=embedding_model))
    return results


def write_jsonl(chunks, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        for chunk in chunks:
            stream.write(json.dumps(chunk.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")
    return path
