package com.bizaid.ai.application;

import com.bizaid.conversation.application.ConversationDtos;
import com.fasterxml.jackson.databind.JsonNode;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;

/**
 * AI 검색·자격 판정의 요청/응답 DTO.
 * FastAPI JSON은 snake_case(request_mode)이고 Java·React는 camelCase(requestMode)다. HttpAiGateway의 전용 ObjectMapper가
 * 이름 규칙만 기계적으로 바꾸며 field 의미·값은 그대로다(contracts/schemas/internal-api·rag-answer·eligibility).
 * 결과 값은 FastAPI가 계산한 것만 담는다. Spring은 답변·순위·판정 상태·근거를 만들거나 고치지 않는다.
 */
public final class AiDtos {

    private AiDtos() {
    }

    /**
     * 자격 판정 때만 쓰는 일시 정보. 기업정보 DB에 저장하지 않는다.
     * 신용점수·체납은 민감하고 자주 바뀌며, additionalFacts는 공고마다 다른 추가 사실(예: "최근 2개월 매출(원)")이다.
     */
    public record TemporaryFacts(Integer creditScore, Boolean taxDelinquent, Map<String, Object> additionalFacts) {
    }

    /** FastAPI POST /internal/v1/eligibility 의 company_profile(CompanyProfileSnapshot)과 같은 field. */
    public record CompanyProfileSnapshot(String companyName, String businessEntityType, String companySize, String region,
                                         String industry, LocalDate businessStartDate, String businessStatus,
                                         Integer employeeCount, Long annualRevenueKrw, Integer creditScore,
                                         Boolean taxDelinquent, Boolean ventureCertified, Boolean researchInstitute,
                                         Boolean exporter, Map<String, Object> additionalFacts) {
    }

    /** Spring 내부에서 AiGateway로 넘기는 판정 요청(공고 ID + 조립된 기업 정보 스냅샷). */
    public record EligibilityCommand(String pblancId, CompanyProfileSnapshot companyProfile) {
    }

    /** 공고문 근거(Citation). location은 자격 판정 근거에만 있고(예: "p.3"), 문서 질문 근거는 pages·headingPath로 위치를 보인다. */
    public record Citation(String evidenceId, Integer rank, String chunkId, String pblancId, String title, List<Integer> pages,
                           String location, String sourceFormat, List<String> headingPath) {
    }

    /** SEARCH_LIST의 공고 한 건. rank·rrfScore 등 순위 근거도 FastAPI 값 그대로다. */
    public record ProgramItem(Integer rank, String pblancId, String name, String category, String target,
                              String jurisdictionName, String executingOrgName, LocalDate applicationStartDate,
                              LocalDate applicationEndDate, String applicationPeriodRaw, String announcementUrl,
                              Double rrfScore, Integer denseRank, Integer sparseRank, String evidenceChunkId) {
    }

    /**
     * FastAPI /internal/v1/query 결과. requestMode는 FastAPI가 정한 값(SEARCH_LIST 또는 DOCUMENT_QA)이다.
     * SEARCH_LIST는 programs, DOCUMENT_QA는 answer·citations를 채운다. naturalFilter는 적용된 조건 진단 정보로 원본 구조를 그대로 둔다.
     */
    public record AiQueryResult(String requestMode, String status, Integer candidateCount, List<ProgramItem> programs,
                                String answer, List<Citation> citations, JsonNode naturalFilter) {
    }

    /** 조건 하나의 판정. result는 MET(충족) / NOT_MET(미충족) / UNKNOWN(판단 불가)이다. */
    public record Criterion(String criterion, String result, String reason, List<String> profileFields,
                            List<String> missingProfileFields, List<Citation> citations) {
    }

    /** status: ELIGIBLE / INELIGIBLE / NEEDS_MORE_INFO / INSUFFICIENT_EVIDENCE (FastAPI가 계산한 값 그대로). */
    public record EligibilityResult(String pblancId, String programName, LocalDate asOf, String status,
                                    List<Criterion> criteria, List<String> missingInformation, String disclaimer) {
    }

    /** React에 돌려주는 AI 검색 응답: 저장된 대화·메시지와 AI 결과. */
    public record AiQueryResponse(Long conversationId, ConversationDtos.MessageResponse userMessage,
                                  ConversationDtos.MessageResponse assistantMessage,
                                  AiQueryResult result) {
    }
}
