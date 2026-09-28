import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from urllib.parse import urlsplit

from biz_aid_pipeline.bizinfo.models import SourceAnnouncement

FIELD_MAPPING = {
    "pblancNm": "name", "pblancUrl": "announcement_url", "jrsdInsttNm": "jurisdiction_name",
    "excInsttNm": "executing_org_name", "bsnsSumryCn": "summary_html",
    "pldirSportRealmLclasCodeNm": "category", "creatPnttm": "source_created_raw",
    "reqstBeginEndDe": "application_period_raw", "updtPnttm": "source_updated_raw",
    "trgetNm": "target", "inqireCo": "inquiry_count", "flpthNm": "attachment_urls_raw",
    "fileNm": "attachment_names_raw", "printFlpthNm": "primary_url_raw", "printFileNm": "primary_filename_raw",
    "hashtags": "hashtags_raw", "reqstMthPapersCn": "application_method_raw", "refrncNm": "contact_raw",
    "rceptEngnHmpgUrl": "application_url_raw",
}


def period(raw):
    if raw is None or not raw.strip():
        return None, None, "UNAVAILABLE"
    match = re.fullmatch(r"(\d{4}-\d{2}-\d{2})\s*~\s*(\d{4}-\d{2}-\d{2})", raw.strip())
    if not match:
        return None, None, "FREE_TEXT"
    try:
        start, end = date.fromisoformat(match[1]), date.fromisoformat(match[2])
        if start > end:
            return None, None, "INVALID_DATE_RANGE"
        return start, end, "DATE_RANGE"
    except ValueError:
        return None, None, "INVALID_DATE_RANGE"


def timestamp(raw):
    if raw is None or not raw.strip():
        return None
    try:
        # 공급자 timezone은 미확정이다. source timestamp에는 timezone을 부여하지 않고 Raw와 함께 저장한다.
        return datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def url_valid(raw):
    if raw is None or not raw.strip():
        return True
    try:
        parsed = urlsplit(raw)
        parsed.port
        return (parsed.scheme in ("http", "https") and bool(parsed.hostname) and not parsed.username
                and not parsed.password and not any(c.isspace() or ord(c) < 32 for c in raw))
    except ValueError:
        return False


@dataclass(frozen=True)
class NormalizedAnnouncement:
    pblanc_id: str
    source_payload: dict
    source_fingerprint: str
    content: dict
    period_class: str
    invalid_urls: int


def normalize(source):
    source = source if isinstance(source, SourceAnnouncement) else SourceAnnouncement.model_validate(source)
    raw = source.raw()
    canonical = json.dumps(raw, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    # Fingerprint 입력은 Source Model뿐이다. 관측시각·Run·DB lifecycle을 섞으면 동일 입력이 UPDATE로 오인된다.
    fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    start, end, category = period(source.reqstBeginEndDe)
    content = {column: getattr(source, name) for name, column in FIELD_MAPPING.items()}
    content.update(application_start_date=start, application_end_date=end,
                   source_created_at=timestamp(source.creatPnttm), source_updated_at=timestamp(source.updtPnttm))
    invalid = sum(not url_valid(value) for name in ("pblancUrl", "flpthNm", "printFlpthNm", "rceptEngnHmpgUrl")
                  for value in ((raw.get(name) or "").split("@") if name == "flpthNm" else [raw.get(name)]))
    return NormalizedAnnouncement(source.pblancId, raw, fingerprint, content, category, invalid)
