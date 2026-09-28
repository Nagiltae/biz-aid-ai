import json
import re
import unicodedata

from docling_core.types.doc import DoclingDocument

CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
WHITESPACE = re.compile(r"\s")


def normalize_text(raw):
    text = unicodedata.normalize("NFC", raw.replace("\r\n", "\n").replace("\r", "\n"))
    cleaned, removed = CONTROL.subn("", text)
    return "\n".join(line.rstrip() for line in cleaned.split("\n")), removed


def normalize_document(document, result):
    # 모든 route의 DoclingDocument에 같은 후처리를 적용하고 추출 원문은 orig에 남겨 정규화 오류를 재현할 수 있게 한다.
    removed = 0
    for item in document.texts:
        raw = item.orig if item.orig is not None else item.text
        item.orig = raw
        item.text, count = normalize_text(raw)
        removed += count
    for table in document.tables:
        for cell in table.data.table_cells:
            cell.text, count = normalize_text(cell.text)
            removed += count
    if removed:
        result.warn("CONTROL_CHARACTERS_REMOVED", removed)


def document_text(document):
    parts = [item.text for item in document.texts]
    parts.extend(cell.text for table in document.tables for cell in table.data.table_cells)
    return "\n".join(parts)


def text_chars(document):
    return len(WHITESPACE.sub("", document_text(document)))


def artifact_bytes(document):
    return json.dumps(document.export_to_dict(), ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def apply_gate(result, document, contract, page_count=None):
    # 예외 없이 끝난 parser 호출만으로 성공 처리하지 않도록 재적재 가능성과 실제 text 양을 함께 판정한다.
    gate = contract["document_gate"]
    result.document = document
    try:
        reloaded = DoclingDocument.model_validate_json(artifact_bytes(document))
    except ValueError:
        result.status, result.failure_code, result.document = "PARSE_FAILED", "artifact_reload_failed", None
        return result
    chars = text_chars(document)
    if text_chars(reloaded) != chars:
        result.status, result.failure_code, result.document = "PARSE_FAILED", "artifact_reload_mismatch", None
        return result
    result.text_chars = chars
    replacement = document_text(document).count("�")
    if replacement and replacement / max(chars, 1) >= gate["replacement_character_warning_ratio"]:
        result.warn("REPLACEMENT_CHARACTERS_PRESENT", replacement)
    if page_count and chars / page_count <= gate["pdf_ocr_required_max_chars_per_page"]:
        # BOUNDARY: OCR은 이번 범위 밖이므로 scan 추정 문서를 실패가 아닌 별도 상태로 드러내고 text를 확정하지 않는다.
        result.status = "OCR_REQUIRED"
    elif chars <= gate["empty_text_max_chars"]:
        result.status = "EMPTY_TEXT"
    else:
        result.status = "PARSED"
    return result
