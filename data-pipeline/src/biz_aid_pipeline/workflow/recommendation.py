"""V2-3 상태 기반 추천 흐름(LangGraph). 개인화 검색 → Top 3 → 공고 1건씩 자격 판정 → 부족 정보 → 사용자 답변 → 필요한 공고만 재판정.

WHY(IMP-020): Top 3 판정을 한 요청에서 연속 실행하면 161초가 걸려 Spring 응답 제한(90초)을 넘었다. 흐름을 단계로 나눠
한 요청은 비싼 판정 LLM 호출을 최대 1건만 하고, 다음에 무엇을 할지는 State가 정한다(클라이언트는 "다음 단계 진행"만 요청).
BOUNDARY: State의 요청 간 저장은 Spring이 MySQL ai_workflows에 한다. 여기서는 받은 State로 한 단계를 실행해 새 State를 돌려줄 뿐
DB에 접근하지 않는다. 검색·판정 규칙·근거 연결·최종 상태 계산은 기존 서비스를 그대로 호출하고 LangGraph 안에 다시 만들지 않는다.
"""
from typing import TypedDict
from uuid import uuid4

from biz_aid_pipeline.config.settings import PipelineError
from biz_aid_pipeline.eligibility.profile import CompanyProfileSnapshot
from biz_aid_pipeline.eligibility.top_programs import PROGRAM_FIELDS, search_profile
from biz_aid_pipeline.observability.tracing import step as trace_step

# 2: COMPLETED State에 final_result 추가(V2-4). 1로 저장된 진행 중 State는 그대로 읽고 다음 단계에서 2로 올린다(추가 필드만 생김).
SCHEMA_VERSION = 2
SUPPORTED_SCHEMA_VERSIONS = (1, 2)
STATUSES = ("IN_PROGRESS", "WAITING_FOR_USER", "COMPLETED", "FAILED")
# 사용자가 이번 판정을 위해 직접 답할 수 있는 기업정보 field. 회사명·추가 사실(공고별 자유 이름)은 받지 않는다.
ANSWERABLE_FIELDS = ("business_entity_type", "company_size", "region", "industry", "business_start_date", "business_status",
                     "employee_count", "annual_revenue_krw", "credit_score", "tax_delinquent", "venture_certified",
                     "research_institute", "exporter")
# 판정이 부족하다고 낸 field → 사용자가 답할 field. 업력(개월)은 저장하지 않는 파생값이라 개업일로 묻는다.
DERIVED_TO_ANSWER = {"business_age_months": "business_start_date"}
CITATION_FIELDS = ("evidence_id", "pblanc_id", "title", "pages", "location", "heading_path")


class RecommendationState(TypedDict, total=False):
    """요청 사이에 JSON으로 저장·복원하는 흐름 상태. 재실행에 필요한 값만 둔다(문서 원문·prompt·secret 없음)."""

    schema_version: int
    query: str
    as_of: str
    company_profile: dict            # Spring이 보낸 영구 기업정보 snapshot(저장된 값만)
    temporary_company_facts: dict    # 이번 workflow에서 사용자가 답한 임시 정보(companies에 저장하지 않음)
    search: dict                     # 개인화 검색 결과(Top 3 포함)
    evaluations: list                # Top 3 순서의 공고별 판정 결과(완료·실패·대기)
    pending: list                    # 아직 판정할 공고 pblanc_id(순서대로, 한 단계에 1건씩 소비)
    missing_information: list        # 공고 결과에서 모은 부족 정보(field ID 기준 중복 제거)
    round: int                       # 판정 회차(0=첫 판정, 1부터 답변 뒤 재판정)
    status: str
    current_step: str
    next_action: str                 # 다음 행동: CONTINUE(다음 단계) / ANSWER(답변 대기) / NONE(끝)
    failure_code: str | None
    final_result: dict | None        # COMPLETED일 때만: 추천·제외·판단 불가(기존 판정 결과를 코드로 조립)
    trace_key: str | None            # 실행 추적 묶음용 무작위 값(V2-6). 사용자·기업 정보와 무관하며 판정에 쓰지 않는다
    # 아래 둘은 한 요청 안에서만 쓰는 입력이며 저장 전에 지운다.
    command: str
    answers: dict


def compact_eligibility(result):
    """판정 결과에서 State에 둘 값만 남긴다. 근거 위치(bbox 등 provenance)·검색 진단은 저장하지 않는다."""
    criteria = [{"criterion": item["criterion"], "result": item["result"], "reason": item["reason"],
                 "profile_fields": item.get("profile_fields", []), "missing_profile_fields": item.get("missing_profile_fields", []),
                 "citations": [{key: citation.get(key) for key in CITATION_FIELDS} for citation in item.get("citations", [])]}
                for item in result.get("criteria", [])]
    return {"pblanc_id": result["pblanc_id"], "program_name": result.get("program_name"), "as_of": result.get("as_of"),
            "status": result["status"], "criteria": criteria, "missing_information": result.get("missing_information", []),
            "disclaimer": result.get("disclaimer"), "llm_seconds": result.get("llm_seconds")}


# 최종 분류: 기존 판정 상태 → 결과 묶음. 새 점수나 LLM 판단 없이 이 표로만 정한다.
FINAL_CATEGORY = {"ELIGIBLE": "recommended", "INELIGIBLE": "excluded", "INSUFFICIENT_EVIDENCE": "unresolved"}
# 묶음별로 이유로 보여 줄 조건 판정 결과(기존 criterion result).
REASON_RESULTS = {"ELIGIBLE": ("MET",), "INELIGIBLE": ("NOT_MET",), "NEEDS_MORE_INFO": ("UNKNOWN",)}
REASON_CODES = {"ELIGIBLE": "all_criteria_met", "INELIGIBLE": "criteria_not_met", "INSUFFICIENT_EVIDENCE": "insufficient_evidence",
                "NEEDS_MORE_INFO": "missing_information_unresolved"}


def final_item(entry):
    """공고 하나의 최종 결과 항목. 이유·근거는 기존 판정 결과에 이미 있는 조건과 검증된 근거만 쓴다(새 문장 생성 없음)."""
    eligibility = entry.get("eligibility")
    base = {"rank": entry["rank"], "pblanc_id": entry["pblanc_id"], "program": entry["program"]}
    if entry["evaluation_status"] != "COMPLETED":
        # 판정 실패: 실패 코드를 그대로 이유로 둔다. UNKNOWN·성공으로 바꾸지 않는다.
        return "unresolved", dict(base, eligibility_status=None, reason_code="evaluation_failed", error_code=entry["error_code"],
                                  reasons=[], missing_information=[], citations=[])
    status = eligibility["status"]
    wanted = REASON_RESULTS.get(status, ())
    chosen = [item for item in eligibility["criteria"] if item["result"] in wanted]
    # 이유는 조건 문구·결과·판정 이유를 그대로 옮기고 근거는 evidence_id로만 가리킨다(근거 본체는 항목의 citations에 한 번만).
    reasons = [{"criterion": item["criterion"], "result": item["result"], "reason": item["reason"],
                "evidence_ids": [citation["evidence_id"] for citation in item["citations"]]} for item in chosen]
    citations, seen = [], set()
    for item in chosen:
        for citation in item["citations"]:
            # BOUNDARY: 근거는 그 공고 판정에서 이미 검증된 것만 다시 쓴다. 다른 공고 근거가 보이면 조립을 멈춘다(걸러 내지 않음).
            if citation["pblanc_id"] != entry["pblanc_id"]:
                raise PipelineError("final_result_cross_program_citation")
            key = citation["evidence_id"]
            if key not in seen:
                seen.add(key)
                citations.append(citation)
    # NEEDS_MORE_INFO가 COMPLETED에 남는 경우는 물어볼 수 없거나 이미 답했는데도 판단 불가인 정보뿐이다. 판단 불가로 둔다.
    category = FINAL_CATEGORY.get(status, "unresolved")
    return category, dict(base, eligibility_status=status, reason_code=REASON_CODES[status], error_code=None, reasons=reasons,
                          missing_information=eligibility["missing_information"] if status == "NEEDS_MORE_INFO" else [],
                          citations=citations)


def build_final_result(evaluations):
    """검색 Top 3 순위(rank) 그대로 추천·제외·판단 불가로 나눈다. 추천이 0건이어도 정상 결과다(가짜 추천 없음)."""
    with trace_step("final_result", evaluation_count=len(evaluations)) as span:
        result = {"recommended": [], "excluded": [], "unresolved": [], "disclaimer": None}
        for entry in sorted(evaluations, key=lambda item: item["rank"]):
            if entry["evaluation_status"] == "PENDING":
                raise PipelineError("final_result_pending_evaluation")
            category, item = final_item(entry)
            result[category].append(item)
            # 안내 문구는 판정 계약의 같은 고정 문구라 항목마다 반복하지 않는다.
            result["disclaimer"] = result["disclaimer"] or (entry.get("eligibility") or {}).get("disclaimer")
        result["counts"] = {key: len(result[key]) for key in ("recommended", "excluded", "unresolved")}
        span.record(**result["counts"])
        return result


def answer_field(name):
    return DERIVED_TO_ANSWER.get(name, name)


def aggregate_missing(evaluations, answered):
    """추가 정보가 필요한 공고의 부족 정보를 field ID 기준으로 합친다. 이미 답한 field는 다시 묻지 않는다(반복 방지)."""
    merged = {}
    for item in evaluations:
        eligibility = item.get("eligibility")
        if item["evaluation_status"] != "COMPLETED" or eligibility["status"] != "NEEDS_MORE_INFO":
            continue
        for name in eligibility["missing_information"]:
            field = answer_field(name)
            if field not in ANSWERABLE_FIELDS or field in answered:
                continue
            entry = merged.setdefault(field, {"field_id": field, "source_fields": [], "programs": []})
            if name not in entry["source_fields"]:
                entry["source_fields"].append(name)
            if item["pblanc_id"] not in entry["programs"]:
                entry["programs"].append(item["pblanc_id"])
    return list(merged.values())


def transition(state, status, current_step, next_action, failure_code=None, evaluations=None):
    """상태 전이는 여기 한 곳에서 한다. Spring은 status·current_step column을 이 값에서 그대로 복사한다.

    COMPLETED로 갈 때만 final_result를 만든다. 아직 답할 부족 정보가 있으면 호출 쪽(aggregate)이 WAITING_FOR_USER로 보낸다.
    """
    if status not in STATUSES:
        raise PipelineError("workflow_invalid_status")
    final = build_final_result(evaluations if evaluations is not None else state.get("evaluations", [])) \
        if status == "COMPLETED" else None
    return {"status": status, "current_step": current_step, "next_action": next_action, "failure_code": failure_code,
            "final_result": final, "schema_version": SCHEMA_VERSION}


def build_graph(search_one, evaluate_one):
    """search_one(query, search_profile, as_of) = V2-1 개인화 검색, evaluate_one(pblanc_id, CompanyProfileSnapshot, as_of) = 기존 단일 판정."""
    from datetime import date
    from langgraph.graph import END, START, StateGraph

    def route(state):
        command = state.get("command")
        if command == "start":
            return "search"
        if command == "continue":
            # BOUNDARY: 다음 행동은 State가 정한다. 진행할 단계가 없는 상태에서 continue는 잘못된 전이다.
            if state.get("status") != "IN_PROGRESS":
                raise PipelineError("workflow_invalid_transition:continue_requires_in_progress")
            return "evaluate_next" if state.get("pending") else "aggregate"
        if command == "answer":
            if state.get("status") != "WAITING_FOR_USER":
                raise PipelineError("workflow_invalid_transition:answer_requires_waiting_for_user")
            return "apply_answers"
        raise PipelineError("workflow_unknown_command")

    def search(state):
        company = CompanyProfileSnapshot.from_dict(state["company_profile"])
        try:
            result = search_one(state["query"], search_profile(company), date.fromisoformat(state["as_of"]))
        except PipelineError as error:
            # 검색 실패는 흐름 전체 실패다. 조용히 빈 결과로 바꾸지 않는다.
            return dict(transition(state, "FAILED", "FAILED", "NONE", str(error)), search=None, evaluations=[], pending=[])
        result = {key: value for key, value in result.items() if key != "natural_filter"}
        programs = result.get("programs", [])
        evaluations = [{"rank": program["rank"], "pblanc_id": program["pblanc_id"],
                        "program": {key: program.get(key) for key in PROGRAM_FIELDS},
                        "evaluation_status": "PENDING", "eligibility": None, "error_code": None, "attempts": 0}
                       for program in programs]
        update = {"search": result, "evaluations": evaluations, "pending": [program["pblanc_id"] for program in programs],
                  "missing_information": [], "round": 0}
        if not programs:
            # 후보 없음·폐업·조건 충돌 등은 판정할 공고가 없으므로 바로 끝난다(검색 상태는 search.status에 그대로 있다).
            return dict(update, **transition(state, "COMPLETED", "DONE", "NONE", evaluations=[]))
        return dict(update, **transition(state, "IN_PROGRESS", "EVALUATE_PROGRAM", "CONTINUE"))

    def evaluate_next(state):
        # BOUNDARY(IMP-020): 한 요청에서 비싼 판정 LLM 호출은 이 노드의 1건뿐이다. 반복은 다음 요청이 한다.
        target, rest = state["pending"][0], state["pending"][1:]
        facts = dict(state["company_profile"], **state.get("temporary_company_facts", {}))
        evaluations = [dict(item) for item in state["evaluations"]]
        item = next(entry for entry in evaluations if entry["pblanc_id"] == target)
        item["attempts"] = item.get("attempts", 0) + 1
        try:
            result = evaluate_one(target, CompanyProfileSnapshot.from_dict(facts), date.fromisoformat(state["as_of"]))
            item.update(evaluation_status="COMPLETED", eligibility=compact_eligibility(result), error_code=None)
        except PipelineError as error:
            # V2-2와 같은 공고별 실패 격리: 이 공고만 FAILED + 코드. UNKNOWN·성공으로 바꾸지 않는다.
            item.update(evaluation_status="FAILED", eligibility=None, error_code=str(error))
        except Exception:
            item.update(evaluation_status="FAILED", eligibility=None, error_code="eligibility_unexpected_error")
        return {"evaluations": evaluations, "pending": rest}

    def after_evaluate(state):
        return END if state["pending"] else "aggregate"

    def aggregate(state):
        missing = aggregate_missing(state["evaluations"], state.get("temporary_company_facts", {}))
        if missing:
            return dict(transition(state, "WAITING_FOR_USER", "AWAIT_ANSWERS", "ANSWER"), missing_information=missing)
        return dict(transition(state, "COMPLETED", "DONE", "NONE"), missing_information=[])

    def apply_answers(state):
        # 답한 값은 보내지 않고 field ID만 기록한다.
        with trace_step("apply_answers", answered_fields=sorted(state.get("answers") or {})) as span:
            update = apply_answers_node(state)
            span.record(reevaluation_targets=len(update.get("pending", [])), status=update.get("status"))
            return update

    def apply_answers_node(state):
        answers = state.get("answers") or {}
        allowed = {item["field_id"] for item in state.get("missing_information", [])}
        # BOUNDARY: 현재 부족 정보에 실제로 있는 field ID만 받는다. 없는 field나 빈 답변은 거부한다.
        if not answers or any(name not in allowed for name in answers):
            raise PipelineError("workflow_answer_field_not_requested")
        temporary = dict(state.get("temporary_company_facts", {}), **answers)
        # 값 형식(숫자·참거짓·날짜·허용값)은 기존 Snapshot 검증으로 확인한다. 틀리면 State를 바꾸지 않는다.
        CompanyProfileSnapshot.from_dict(dict(state["company_profile"], **temporary))
        answered = set(answers)
        # 재판정 대상: 답한 field 때문에 정보 부족이던 공고만. Top 3 전체를 다시 판정하지 않는다.
        targets = [entry["pblanc_id"] for entry in state["evaluations"]
                   if entry["evaluation_status"] == "COMPLETED" and entry["eligibility"]["status"] == "NEEDS_MORE_INFO"
                   and answered & {answer_field(name) for name in entry["eligibility"]["missing_information"]}]
        update = {"temporary_company_facts": temporary, "pending": targets, "round": state.get("round", 0) + 1,
                  "missing_information": []}
        if not targets:
            return dict(update, **transition(state, "COMPLETED", "DONE", "NONE"))
        return dict(update, **transition(state, "IN_PROGRESS", "EVALUATE_PROGRAM", "CONTINUE"))

    graph = StateGraph(RecommendationState)
    for name, node in (("search", search), ("evaluate_next", evaluate_next), ("aggregate", aggregate),
                       ("apply_answers", apply_answers)):
        graph.add_node(name, node)
    graph.add_conditional_edges(START, route, ["search", "evaluate_next", "aggregate", "apply_answers"])
    graph.add_edge("search", END)
    graph.add_conditional_edges("evaluate_next", after_evaluate, ["aggregate", END])
    graph.add_edge("aggregate", END)
    graph.add_edge("apply_answers", END)
    return graph.compile()


def strip_inputs(state):
    """요청 입력(command·answers)은 저장 대상이 아니다."""
    return {key: value for key, value in state.items() if key not in ("command", "answers")}


def start(graph, query, company_profile, as_of, trace_key=None):
    state = {"schema_version": SCHEMA_VERSION, "query": query, "as_of": str(as_of), "company_profile": dict(company_profile),
             "temporary_company_facts": {}, "status": "IN_PROGRESS", "current_step": "SEARCH", "next_action": "CONTINUE",
             "failure_code": None, "command": "start", "trace_key": trace_key or uuid4().hex}
    return strip_inputs(graph.invoke(state))


def advance(graph, state, command, answers=None):
    if not isinstance(state, dict) or state.get("schema_version") not in SUPPORTED_SCHEMA_VERSIONS:
        raise PipelineError("workflow_state_version_unsupported")
    return strip_inputs(graph.invoke(dict(state, command=command, answers=answers or {})))
