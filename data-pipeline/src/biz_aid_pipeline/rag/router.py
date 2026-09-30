"""request_mode에 따라 SEARCH_LIST(공고 목록) 또는 DOCUMENT_QA(기존 근거 답변)로 보낸다. 새 판단을 하지 않는 얇은 분기다."""


def handle_request(query, request_mode, candidate_pblanc_ids, rag_service, discovery_service):
    # WHY: "찾아줘" 같은 목록 요청은 문서 하나의 QA가 아니다. MySQL 정형 정보 목록으로 답하고 생성 LLM을 부르지 않는다.
    if request_mode == "SEARCH_LIST":
        programs = discovery_service.discover(query, candidate_pblanc_ids)
        status = "NO_CANDIDATES" if not candidate_pblanc_ids else ("LISTED" if programs else "NO_INDEXED_PROGRAMS")
        return {"request_mode": request_mode, "status": status, "candidate_count": len(candidate_pblanc_ids), "programs": programs}
    result = rag_service.answer(query, candidate_pblanc_ids=candidate_pblanc_ids).to_dict()
    return dict(result, request_mode="DOCUMENT_QA")
