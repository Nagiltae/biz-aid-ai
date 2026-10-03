"""조각 출처 종류(document_role) 판정: 공고 본문(BODY)·신청 양식(FORM)·목록(LIST)·미상(UNKNOWN).

형식과 원본 파일명 단서만 쓰는 단순 규칙이다. 빈 신청 양식이 본문 근거를 밀어내는지 cases-v2에서 재기 위한 기록용이며,
목록 순위에는 쓰지 않고 FORM은 판정·문서 답변 근거에서만 제외한다. parse_key·chunk_set_key·embedding_text·embedding_key의 입력이 아니다.
"""
import unicodedata

from biz_aid_pipeline.indexing.embedder import indexing_contract

ROLES = ("BODY", "FORM", "LIST", "UNKNOWN")
PRIORITY = ("FORM", "LIST", "BODY")


def normalize(name):
    return "".join(unicodedata.normalize("NFC", name or "").lower().split())


def filename_role(detected_format, filename, spec):
    text = normalize(filename)
    # WHY: 내부 지급 규정은 지원사업 본문이라는 증거가 아니다. 업무 지침 단서는 보존한다.
    if any(normalize(cue) in text for cue in spec.get("internal_policy_cues", ())):
        return "UNKNOWN"
    for role in PRIORITY:
        if any(normalize(cue) in text for cue in spec["filename_cues"][role]):
            return role
        # WHY: "제출서류"는 양식 묶음과 제출 서류 안내문 이름에 모두 쓰인다. 함께 쓰인 단어로만 종류를 정한다.
        if any(rule["role"] == role and normalize(rule["cue"]) in text and any(normalize(word) in text for word in rule["with_any"])
               for rule in spec.get("qualified_cues", ())):
            return role
    return spec["format_defaults"].get(detected_format, "UNKNOWN")


def document_role(detected_format, filenames, contract=None):
    """한 원본(같은 SHA)에 연결된 파일명들의 판정이 하나로 모이면 그 값, 엇갈리거나 없으면 UNKNOWN."""
    spec = (contract or indexing_contract())["document_role"]
    roles = {filename_role(detected_format, name, spec) for name in filenames if name}
    if not roles:
        return spec["format_defaults"].get(detected_format, "UNKNOWN")
    return roles.pop() if len(roles) == 1 else "UNKNOWN"
