"""명확한 질문 의도와 공고 이름 선택. 모호한 의도는 기존 LLM, 공고 동점은 사용자에게 맡긴다."""
import re
import unicodedata
from datetime import date

from biz_aid_pipeline.config.settings import PipelineError
from biz_aid_pipeline.rag.service import rag_contract


def compact(value):
    return re.sub(r"[^가-힣a-z0-9]", "", unicodedata.normalize("NFC", value or "").lower())


def name_matches(query, metadata, spec=None):
    spec = spec or rag_contract()["question_routing"]
    q = compact(query)
    cut = min((q.find(compact(term)) for term in spec["detail_phrases"] if compact(term) in q), default=len(q))
    subject = q[:cut]
    for suffix in spec["name_suffixes"]:
        suffix = compact(suffix)
        if subject.endswith(suffix):
            subject = subject[:-len(suffix)]
    matches = []
    for row in metadata.values():
        name = compact(row.get("name"))
        if not name:
            continue
        if name in q:
            score = (3 if name == subject else 2, len(name))
        elif len(subject) >= spec["minimum_name_chars"] and subject in name:
            score = (1, len(subject))
        else:
            continue
        matches.append((score, row))
    return matches


def deterministic_mode(query, metadata):
    spec, q = rag_contract()["question_routing"], compact(query)
    if any(compact(word) in q for word in spec["list_phrases"]):
        return "SEARCH_LIST"
    if any(compact(word) in q for word in spec["detail_phrases"]) and name_matches(query, metadata, spec):
        return "DOCUMENT_QA"
    return None


def choose_program(query, metadata, as_of=None, selected_id=None):
    if selected_id is not None:
        if selected_id not in metadata:
            raise PipelineError("query_program_not_found_or_inactive")
        return (selected_id,), []
    matches = name_matches(query, metadata)
    if not matches:
        # 특정 공고명이 없는 일반 문서 질문의 기존 후보 범위는 유지한다.
        return tuple(metadata), []
    day = as_of or date.today()
    def key(item):
        score, row = item
        start, end = row.get("application_start_date"), row.get("application_end_date")
        opened = bool(start and end and str(start) <= str(day) <= str(end))
        return (*score, opened, str(row.get("source_created_at") or ""))
    matches.sort(key=lambda item: (key(item), item[1]["pblanc_id"]), reverse=True)
    best = key(matches[0])
    tied = [row for item in matches if key(item) == best for row in [item[1]]]
    if len(tied) == 1:
        return (tied[0]["pblanc_id"],), []
    fields = ("pblanc_id", "name", "jurisdiction_name", "application_start_date", "application_end_date", "application_period_raw")
    options = [{field: str(row[field]) if row.get(field) is not None else None for field in fields}
               for row in tied[:rag_contract()["question_routing"]["candidate_limit"]]]
    return (), options
