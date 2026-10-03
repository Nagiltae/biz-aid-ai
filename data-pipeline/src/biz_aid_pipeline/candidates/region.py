"""기업 지역(광역 지자체) 규칙. 표준명·소관기관 매핑은 계약(company-region.contract.json)에만 있고 코드에 적지 않는다.

2026-10-03 사용자 결정(IMP-019 지역 부분): 기업 지역과 다른 광역 지자체가 소관기관인 공고만 후보에서 뺀다.
중앙부처·공공기관·매핑에 없는 소관기관은 남긴다(fail-open).
"""
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
