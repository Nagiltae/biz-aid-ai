"""질문 → Hybrid Retriever top5 → evidence context → LlmProvider → 근거 답변 + application이 만든 citation.

LLM은 request-local evidence id(E1..En)만 고른다. citation의 chunk_id·pblanc_id·page·source·provenance는
모델 출력이 아니라 이번 요청에서 실제로 검색된 SearchResult에서만 가져온다.
"""
import copy
import json
import re
from dataclasses import asdict, dataclass, field

from biz_aid_pipeline.config.settings import ROOT, PipelineError, read_json
from biz_aid_pipeline.rag.llm import LlmRequest

CONTRACT_PATH = ROOT / "contracts/schemas/rag-answer.contract.json"

SYSTEM_PROMPT = """너는 중소기업 지원사업 공고문 근거만으로 답하는 도우미다.
규칙:
1. 아래 [E번호] evidence에 적힌 내용만 근거로 답한다. 일반 지식이나 추측으로 빈 내용을 채우지 않는다.
2. 숫자·날짜·금액·자격 조건은 evidence에 적힌 그대로만 쓰고, 없는 값을 보완하거나 계산해 만들지 않는다.
3. evidence끼리 내용이 서로 다르면 다르다는 사실과 각각의 evidence 번호를 함께 밝힌다.
4. 질문에 답할 근거가 evidence에 없으면 insufficient_evidence를 true로 하고 "제공된 공고문 근거만으로는 확인할 수 없습니다"라고 답한다.
5. 답에 실제로 사용한 evidence 번호만 evidence_ids에 넣는다(예: ["E1", "E3"]). 다른 식별자나 출처 정보를 만들지 않는다.
6. 한국어로 간결하게 답하고, 결과는 지정된 JSON 형식으로만 출력한다."""


def rag_contract(path=CONTRACT_PATH):
    return read_json(path)


@dataclass
class Citation:
    evidence_id: str
    rank: int
    chunk_id: str
    pblanc_id: str
    title: str | None
    pages: list
    source_sha256: str
    source_format: str
    heading_path: list
    provenance: list


@dataclass
class RagAnswer:
    query: str
    status: str
    answer: str
    citations: list
    used_evidence_ids: list
    rejected_evidence_ids: list
    retrieved: list
    provider: str
    model: str
    llm_seconds: float
    discarded_answer: str | None = None
    usage: dict = field(default_factory=dict)
    candidate_count: int | None = None

    def to_dict(self):
        return asdict(self)


def location(result):
    """사람이 읽는 위치. page가 있으면 page, HWPX처럼 page가 없으면 section 이름만 쓴다."""
    if result.pages:
        return "p." + ", ".join(str(page) for page in result.pages)
    sections = sorted({entry.get("section") for entry in result.provenance if entry.get("section")})
    return ("HWPX " + ", ".join(sections)) if sections else "위치 정보 없음"


def readable_evidence(text):
    """triplet 표를 평평한 cell 목록으로 표시한다. row/span을 새로 추정하거나 저장된 chunk를 바꾸지 않는다."""
    spec = rag_contract().get("context_table_presentation", {})
    if not spec.get("enabled"):
        return text
    pattern = r"([^\n.]+?),\s*(\d+)\s*=\s*(.*?)(?=\.\s*[^\n.]+?,\s*\d+\s*=|$)"
    rows = list(re.finditer(pattern, text, flags=re.S))
    # BOUNDARY: 원문 전체가 triplet 표임을 확인할 때만 표시를 바꾼다. 자유문장 일부를 임의로 표 구조로 만들지 않는다.
    if len(rows) < 2 or text[:rows[0].start()].strip():
        return text
    lines = ["표 cell 목록 (행·병합 구조는 추정하지 않음):"]
    for row in rows:
        lines.append(f"- {row.group(1).strip()} / 열 {row.group(2)}: {row.group(3).strip()}")
    return "\n".join(lines)


def build_context(results):
    """검색 결과를 [E1]..[En] 블록으로 만든다. 식별자·점수·원본 payload는 넣지 않는다."""
    blocks, index = [], {}
    for number, result in enumerate(results, 1):
        evidence_id = f"E{number}"
        index[evidence_id] = result
        heading = " > ".join(result.heading_path) if result.heading_path else "-"
        blocks.append(f"[{evidence_id}]\n공고: {result.title or '-'}\n위치: {location(result)}\n문단 제목: {heading}\n내용:\n{readable_evidence(result.text)}")
    return "\n\n".join(blocks), index


def answer_schema(base, index):
    """이번 context의 evidence 번호만 고르게 생성 단계에서 제한한다(enum). 근거가 없으면 기본 schema 그대로다.

    제한해도 parse_output·used/rejected 검증은 그대로 한다(생성 제한 + application 재검증의 이중 방어).
    """
    if not index:
        return base
    schema = copy.deepcopy(base)
    schema["properties"]["evidence_ids"]["items"]["enum"] = list(index)
    return schema


def parse_output(text):
    try:
        value = json.loads(text)
    except ValueError:
        raise PipelineError("rag_llm_output_not_json") from None
    if not isinstance(value, dict) or not isinstance(value.get("answer"), str) or not isinstance(value.get("evidence_ids"), list):
        raise PipelineError("rag_llm_output_schema_mismatch")
    return value


class RagService:
    def __init__(self, retriever, provider, contract=None):
        self.retriever, self.provider = retriever, provider
        self.contract = contract or rag_contract()

    def answer(self, query, candidate_pblanc_ids=None):
        """candidate_pblanc_ids(MySQL 후보)를 주면 그 공고 안에서만 검색하고 답한다. None은 scope 없는 dev·test 호출이다."""
        spec = self.contract["retrieval"]
        if candidate_pblanc_ids is not None:
            candidates = tuple(candidate_pblanc_ids)
            # BOUNDARY: 정형 조건에 맞는 공고가 없으면 검색·LLM을 호출하지 않는다. 모델에게 후보 없는 답을 만들게 하지 않는다.
            if not candidates:
                return RagAnswer(query, "NO_CANDIDATES", self.contract["status"]["no_candidates_message"], [], [], [], [],
                                 self.provider.name, self.provider.model, 0.0, candidate_count=0)
            results = self.retriever.search(query, spec["mode"], spec["top_k"], pblanc_ids=candidates, exclude_roles=("FORM",))
            allowed = set(candidates)
            # RISK: scope는 Qdrant filter가 강제하지만, 후보 밖 결과가 오면 근거로 쓰지 않고 실패시킨다.
            if any(result.pblanc_id not in allowed for result in results):
                raise PipelineError("retrieval_scope_violation")
        else:
            results = self.retriever.search(query, spec["mode"], spec["top_k"], exclude_roles=("FORM",))
        context, index = build_context(results)
        user = f"질문: {query}\n\n근거(evidence):\n{context}" if results else f"질문: {query}\n\n근거(evidence): 없음"
        response = self.provider.generate(LlmRequest(SYSTEM_PROMPT, user, answer_schema(self.contract["output_schema"], index)))
        output = parse_output(response.text)
        chosen = list(dict.fromkeys(str(item) for item in output["evidence_ids"]))
        # BOUNDARY: 이번 context에 없는 id는 citation으로 만들지 않는다. 모델이 지어낸 출처가 사용자에게 가지 않게 한다.
        used = [evidence_id for evidence_id in chosen if evidence_id in index]
        rejected = [evidence_id for evidence_id in chosen if evidence_id not in index]
        status, answer, discarded = "ANSWERED", output["answer"].strip(), None
        # RISK: 근거 id 없는 답은 검증할 수 없어 근거 기반 답으로 내보내지 않는다. 모델 원문은 진단용으로만 남긴다.
        if output.get("insufficient_evidence") or not used:
            status, discarded, used = "INSUFFICIENT_EVIDENCE", answer or None, []
            answer = self.contract["status"]["insufficient_message"]
        citations = [Citation(evidence_id, index[evidence_id].rank, index[evidence_id].chunk_id, index[evidence_id].pblanc_id,
                              index[evidence_id].title, index[evidence_id].pages, index[evidence_id].source_sha256,
                              index[evidence_id].source_format, index[evidence_id].heading_path, index[evidence_id].provenance)
                     for evidence_id in used]
        retrieved = [{"evidence_id": evidence_id, "rank": result.rank, "chunk_id": result.chunk_id, "pblanc_id": result.pblanc_id}
                     for evidence_id, result in index.items()]
        return RagAnswer(query, status, answer, citations, used, rejected, retrieved, response.provider, response.model,
                         response.elapsed_seconds, discarded, response.usage,
                         len(candidate_pblanc_ids) if candidate_pblanc_ids is not None else None)
