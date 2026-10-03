"""기업 지역(광역 지자체) 규칙. 표준명·소관기관 매핑은 계약(company-region.contract.json)에만 있고 코드에 적지 않는다.

소관·제목 지역 표시는 신청 가능 지역의 대리 지표다. 미매핑은 fail-open이고 실제 자격 AI 추출은 하지 않는다.
"""
import re
from functools import lru_cache

from biz_aid_pipeline.config.settings import ROOT, read_json

CONTRACT_PATH = ROOT / "contracts/schemas/company-region.contract.json"


@lru_cache(maxsize=1)
def region_contract(path=CONTRACT_PATH):
    return read_json(path)


def standard_regions(contract=None):
    return tuple((contract or region_contract())["regions"])


def excluded_jurisdictions(region, contract=None):
    """기업 지역이 표준명이면 다른 광역 소관기관 목록, 아니면 None(지역 조건을 적용하지 않음)."""
    contract = contract or region_contract()
    if region not in contract["regions"]:
        return None
    return tuple(sorted(name for name, owner in contract["jurisdiction_regions"].items() if owner != region))


def title_regions(name, contract=None):
    """공고명 맨 앞의 지역 표시만 해석한다. 미매핑 token 하나라도 있으면 제한을 추측하지 않는다."""
    contract = contract or region_contract()
    match = re.match(r"^\s*\[([^\]]+)\]", name or "")
    if not match:
        return ()
    aliases = {alias: region for region, values in contract["aliases"].items() for alias in values}
    spec = contract["title_region_rule"]
    pattern = "|".join(re.escape(value) for value in spec["separators"])
    tokens = re.split(pattern, match[1])
    regions = set()
    for token in tokens:
        token = token.strip()
        if token in aliases:
            regions.add(aliases[token])
        elif token in spec["area_aliases"]:
            regions.update(spec["area_aliases"][token])
        else:
            return ()
    return tuple(sorted(regions))


def program_regions(name, jurisdiction, contract=None):
    """복수 제목 지역 → 소관 광역 → 중앙/미매핑 제목 지역 순서. 업무상 신청 자격을 확정하지 않는다."""
    contract = contract or region_contract()
    tagged = title_regions(name, contract)
    if len(tagged) > 1:
        return tagged, "TITLE_REGION"
    owner = contract["jurisdiction_regions"].get(jurisdiction)
    if owner:
        return (owner,), "JURISDICTION"
    if tagged:
        return tagged, "TITLE_REGION"
    return (), "NATIONWIDE_OR_UNMAPPED"


def region_allowed(region, name, jurisdiction):
    regions, _ = program_regions(name, jurisdiction)
    return region not in standard_regions() or not regions or region in regions
