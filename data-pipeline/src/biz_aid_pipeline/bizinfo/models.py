import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, StrictInt, StrictStr, field_validator


class SourceAnnouncement(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True, frozen=True)
    pblancId: StrictStr
    pblancNm: StrictStr | None = None
    pblancUrl: StrictStr | None = None
    jrsdInsttNm: StrictStr | None = None
    excInsttNm: StrictStr | None = None
    bsnsSumryCn: StrictStr | None = None
    pldirSportRealmLclasCodeNm: StrictStr | None = None
    creatPnttm: StrictStr | None = None
    reqstBeginEndDe: StrictStr | None = None
    updtPnttm: StrictStr | None = None
    trgetNm: StrictStr | None = None
    inqireCo: StrictInt | None = None
    flpthNm: StrictStr | None = None
    fileNm: StrictStr | None = None
    printFlpthNm: StrictStr | None = None
    printFileNm: StrictStr | None = None
    hashtags: StrictStr | None = None
    reqstMthPapersCn: StrictStr | None = None
    refrncNm: StrictStr | None = None
    rceptEngnHmpgUrl: StrictStr | None = None

    @field_validator("pblancId")
    @classmethod
    def identifier(cls, value):
        # 식별자를 trim·대소문자 변환하면 다른 원문이 같은 DB business key로 합쳐질 수 있다.
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", value):
            raise ValueError("invalid_business_key")
        return value

    def raw(self):
        # Key 없음·JSON null·빈 문자열·미지 field는 audit와 재정규화에 필요한 서로 다른 원문 상태다.
        return self.model_dump(exclude_unset=True)


class SyncScope(str, Enum):
    SAMPLE = "SAMPLE"
    PARTIAL = "PARTIAL"
    FULL = "FULL"


@dataclass(frozen=True)
class SourcePage:
    number: int
    requested_rows: int
    items: tuple[dict[str, Any], ...] = field(repr=False)
    total_count: int | None = None
    outcome: str = "SUCCESS"
    http_status: int | None = 200
    result_code: str | None = "00"
    result_message: str | None = "NORMAL_SERVICE"
    echo_matches: bool = True


@dataclass(frozen=True)
class SourceBatch:
    scope: SyncScope
    pages: tuple[SourcePage, ...]
    sample: str
    pagination_terminated: bool = False
    provenance: dict[str, Any] = field(default_factory=dict)

    @property
    def items(self):
        return [item for page in self.pages if page.outcome == "SUCCESS" for item in page.items]
