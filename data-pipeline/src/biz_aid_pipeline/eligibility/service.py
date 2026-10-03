"""공고 1개 + 기업 Profile snapshot → 공고 근거 기반 criterion 판정 → application이 최종 status 계산.

LLM은 criterion별 MET·NOT_MET·UNKNOWN과 근거 evidence id·사용한 profile field만 낸다.
최종 status·citation·누락 정보는 application이 검증된 결과로 만든다. 설명 생성 LLM 호출은 없다.
"""
import copy
import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from biz_aid_pipeline.config.settings import ROOT, PipelineError, read_json
from biz_aid_pipeline.rag.llm import LlmRequest
from biz_aid_pipeline.rag.service import build_context, location

CONTRACT_PATH = ROOT / "contracts/schemas/eligibility.contract.json"
RESULTS = ("MET", "NOT_MET", "UNKNOWN")

SYSTEM_PROMPT = """너는 지원사업 공고의 자격 요건과 기업 정보를 비교하는 도구다. 추천·설명 문장을 만들지 않는다.
규칙:
1. [E번호] evidence에 적힌 지원 대상·자격·요건·제외(제한) 조건만 criterion으로 만든다. 제출 서류·신청 절차·작성 항목·기간·지원 내용은 criterion이 아니다. 서류 목록에 등장하는 항목을 지원 자격으로 바꾸지 않는다.
2. 논리적으로 하나인 조건은 하나의 criterion으로 둔다. "A 또는 B"는 한 criterion이며 둘 중 하나라도 충족하면 MET이다. 같은 조건을 쪼개지 않는다. 같은 조건을 두 번 쓰지 않는다. 관련 조건은 하나로 묶는다(보통 2~8개).
   조건 수를 맞추기 위해 근거의 독립적인 필수 요건을 생략하지 않는다.
   예외·완화 규정(예: 특정 피해 기업은 기준 완화)은 원래 조건과 같은 criterion에 포함하고 따로 만들지 않는다.
3. 제외·제한 조건(예: 체납 중, 휴·폐업)은 기업이 해당하지 않으면 MET, 해당하면 NOT_MET이다.
4. 판단에 필요한 기업 정보가 null이거나 목록에 없으면 추측하지 말고 UNKNOWN으로 한다. 일반 지식으로 보완하지 않는다.
   기업 정보는 field ID(예: credit_score, extra_1)로 주어진다. extra_N은 아래 설명에 적힌 추가 사실이다.
5. 숫자·날짜는 evidence와 기업 정보에 적힌 값만 비교한다. 업력은 business_age_months(개월)를 쓴다.
6. 각 criterion에 근거 evidence 번호(evidence_ids)와 비교에 쓴 기업 정보 field ID(profile_fields)를 반드시 넣는다. 주어진 ID만 그대로 쓴다.
7. reason은 한 문장으로 짧게 쓴다. 결과는 지정된 JSON 형식으로만 출력한다."""

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"criteria": {"type": "array", "items": {
        "type": "object",
        "properties": {"criterion": {"type": "string"}, "result": {"type": "string", "enum": list(RESULTS)},
                       "reason": {"type": "string"}, "evidence_ids": {"type": "array", "minItems": 1, "items": {"type": "string"}},
                       "profile_fields": {"type": "array", "items": {"type": "string"}}},
        "required": ["criterion", "result", "reason", "evidence_ids", "profile_fields"]}}},
    "required": ["criteria"],
}


def eligibility_contract(path=CONTRACT_PATH):
    return read_json(path)


def fact_ids(facts):
    """기업 사실에 LLM이 그대로 고를 안정적인 field ID를 붙인다. 반환: ({ID: 값}, {ID: 원래 이름}, {ID: 사람이 읽는 설명}).

    WHY(V1 baseline E01·E03): 추가 사실은 사람이 읽는 한국어 이름(예: "최근 2개월 매출(원)")이라 모델이 띄어쓰기·단위를 바꿔
    다시 써서 계약 검증에 걸렸다. 기본 field는 이미 고정 영문 ID이고, 추가 사실은 순서대로 extra_1, extra_2 …를 쓴다.
    결과에는 원래 이름으로 되돌려 API 응답 의미(missing_information 등)를 바꾸지 않는다.
    """
    by_id, names, labels, extra = {}, {}, {}, 0
    for name, value in facts.items():
        if name.startswith("additional_facts."):
            extra += 1
            key = f"extra_{extra}"
            labels[key] = name.removeprefix("additional_facts.")
        else:
            key = name
        by_id[key], names[key] = value, name
    return by_id, names, labels


def output_schema(allowed_fields, allowed_evidence, max_criteria=None):
    """요청마다 허용값을 넣은 출력 schema. 고를 수 있는 field ID·evidence 번호를 생성 단계에서 미리 제한한다(enum).

    max_criteria는 criteria 배열 최대 개수(maxItems)다. 같은 조건을 끝없이 반복 생성하는 폭주를 생성 단계에서 끊는다.
    """
    schema = copy.deepcopy(OUTPUT_SCHEMA)
    if max_criteria:
        schema["properties"]["criteria"]["maxItems"] = max_criteria
    item = schema["properties"]["criteria"]["items"]["properties"]
    item["evidence_ids"]["items"]["enum"] = list(allowed_evidence)
    item["profile_fields"]["items"]["enum"] = list(allowed_fields)
    return schema


def overall_status(criteria):
    """검증된 criterion 결과만으로 최종 상태를 정한다. 모델이 따로 낸 종합 판단은 쓰지 않는다."""
    if not criteria:
        return "INSUFFICIENT_EVIDENCE"
    results = {item["result"] for item in criteria}
    if "NOT_MET" in results:
        return "INELIGIBLE"
    if "UNKNOWN" in results:
        return "NEEDS_MORE_INFO"
    return "ELIGIBLE"


def citation(evidence_id, result):
    return {"evidence_id": evidence_id, "rank": result.rank, "chunk_id": result.chunk_id, "pblanc_id": result.pblanc_id,
            "title": result.title, "pages": result.pages, "location": location(result), "source_sha256": result.source_sha256,
            "heading_path": result.heading_path, "provenance": result.provenance}


def validate(raw, index, facts, pblanc_id, names=None):
    """LLM criterion을 검증한다. 형식·id·field 위반은 실패시키고, 값 없는 정보로 낸 MET·NOT_MET은 UNKNOWN으로 되돌린다.

    facts는 {field ID: 값}이다. 생성 단계에서 enum으로 제한했더라도 여기서 다시 검증한다(provider가 schema를 어길 수 있다).
    names가 있으면 결과의 field를 원래 이름으로 되돌린다.
    """
    names = names or {key: key for key in facts}
    if not isinstance(raw, dict) or not isinstance(raw.get("criteria"), list):
        raise PipelineError("eligibility_output_schema_mismatch")
    validated = []
    for item in raw["criteria"]:
        if (not isinstance(item, dict) or item.get("result") not in RESULTS or not isinstance(item.get("criterion"), str)
                or not isinstance(item.get("reason"), str) or not isinstance(item.get("evidence_ids"), list)
                or not isinstance(item.get("profile_fields"), list)):
            raise PipelineError("eligibility_output_schema_mismatch")
        evidence_ids = list(dict.fromkeys(str(value) for value in item["evidence_ids"]))
        # BOUNDARY: 근거 없는 criterion, 이번 context에 없는 id, 다른 공고의 evidence는 받지 않는다(조용한 fallback 없음).
        if not evidence_ids or any(value not in index for value in evidence_ids):
            logging.getLogger(__name__).warning("eligibility_invalid_evidence_id empty=%s outside_count=%d",
                                               not evidence_ids, sum(value not in index for value in evidence_ids))
            raise PipelineError("eligibility_invalid_evidence_id")
        if any(index[value].pblanc_id != pblanc_id for value in evidence_ids):
            raise PipelineError("eligibility_cross_program_evidence")
        # 허용된 field ID만 받는다. 목록 밖 ID는 고쳐 쓰지 않고 실패시킨다.
        profile_fields = list(dict.fromkeys(str(value) for value in item["profile_fields"]))
        unknown = [value for value in profile_fields if value not in facts]
        if unknown:
            raise PipelineError("eligibility_unknown_profile_field:" + ",".join(unknown))
        result, adjusted = item["result"], None
        # RISK: 비교할 기업 값이 하나도 없는데 MET·NOT_MET이면 모델이 추측한 것이다. application이 UNKNOWN으로 되돌린다.
        if result != "UNKNOWN" and not any(facts[value] is not None for value in profile_fields):
            result, adjusted = "UNKNOWN", f"model_{item['result']}_without_profile_value"
        validated.append({"criterion": item["criterion"].strip(), "result": result, "reason": item["reason"].strip(),
                          "evidence_ids": evidence_ids, "profile_fields": [names[value] for value in profile_fields],
                          "missing_profile_fields": [names[value] for value in profile_fields if facts[value] is None],
                          "adjusted": adjusted, "citations": [citation(value, index[value]) for value in evidence_ids]})
    return validated


class EligibilityService:
    def __init__(self, repository, retriever, provider, contract=None):
        self.repository, self.retriever, self.provider = repository, retriever, provider
        self.contract = contract or eligibility_contract()

    def evaluate(self, pblanc_id, profile, as_of=None):
        spec = self.contract["retrieval"]
        as_of = as_of or datetime.now(ZoneInfo("Asia/Seoul")).date()
        program = self.repository.program_metadata([pblanc_id]).get(pblanc_id)
        # BOUNDARY: 존재하지 않거나 비활성·삭제된 공고는 판정 대상이 아니다(support_programs lifecycle 그대로).
        if program is None:
            raise PipelineError("eligibility_program_not_found_or_inactive")
        # 검색 질의는 application이 정한 고정 문구다. 기업 정보를 넣어 검색을 한쪽으로 치우치게 하지 않는다.
        results = self.retriever.search(spec["query"], spec["mode"], spec["top_k"], pblanc_ids=(pblanc_id,), exclude_roles=("FORM",))
        if any(result.pblanc_id != pblanc_id for result in results):
            raise PipelineError("retrieval_scope_violation")
        base = {"pblanc_id": pblanc_id, "program_name": program["name"], "as_of": str(as_of),
                "disclaimer": self.contract["disclaimer"], "provider": self.provider.name, "model": self.provider.model}
        if not results:
            return dict(base, status="INSUFFICIENT_EVIDENCE", criteria=[], missing_information=[], explanation=[],
                        retrieved=[], llm_seconds=0.0)
        context, index = build_context(results)
        facts, names, labels = fact_ids(profile.facts(as_of))
        legend = "".join(f"\n- {key}: {label}" for key, label in labels.items())
        user = (f"기준일: {as_of}\n\n공고 근거(evidence):\n{context}\n\n기업 정보(field ID: 값, null은 모름):\n"
                f"{json.dumps(facts, ensure_ascii=False, indent=1)}" + (f"\n\n추가 사실 field ID 설명:{legend}" if legend else ""))
        limits = self.contract["criterion_output"]
        response = self.provider.generate(LlmRequest(SYSTEM_PROMPT, user, output_schema(facts, index, limits["max_criteria"]),
                                                     max_output_tokens=limits["max_output_tokens"]))
        # BOUNDARY: 출력 상한에 닿은 결과는 잘린 목록일 수 있다. 빠진 조건 때문에 ELIGIBLE이 되지 않게 판정하지 않고 실패로 남긴다.
        if response.usage.get("done_reason") == "length":
            raise PipelineError("eligibility_output_limit_reached")
        try:
            raw = json.loads(response.text)
        except ValueError:
            raise PipelineError("eligibility_output_not_json") from None
        if isinstance(raw, dict) and isinstance(raw.get("criteria"), list) and len(raw["criteria"]) >= limits["max_criteria"]:
            raise PipelineError("eligibility_output_limit_reached")
        criteria = validate(raw, index, facts, pblanc_id, names)
        status = overall_status(criteria)
        missing = sorted({field for item in criteria if item["result"] == "UNKNOWN" for field in item["missing_profile_fields"]})
        explanation = [f"[{item['result']}] {item['criterion']}: {item['reason']}" for item in criteria]
        retrieved = [{"evidence_id": key, "chunk_id": value.chunk_id, "pblanc_id": value.pblanc_id, "location": location(value)}
                     for key, value in index.items()]
        return dict(base, status=status, criteria=criteria, missing_information=missing, explanation=explanation,
                    retrieved=retrieved, llm_seconds=response.elapsed_seconds)
