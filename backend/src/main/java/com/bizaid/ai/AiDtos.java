package com.bizaid.ai;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.PositiveOrZero;
import jakarta.validation.constraints.Size;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;

/**
 * AI 검색·자격 판정의 사용자용 요청/응답과, 이후 FastAPI 내부 API로 보낼 요청 형태.
 * 응답 필드는 FastAPI 결과(contracts/schemas/rag-answer·eligibility)를 React가 쓰기 쉬운 camelCase로 옮긴 것이다.
 * 결과 값은 FastAPI가 계산한 것만 담는다. Spring이 판정·답변을 만들거나 고치지 않는다.
 */
public final class AiDtos {

    private AiDtos() {
    }

    public record AiQueryRequest(
            @NotBlank(message = "질문을 입력해 주세요.") @Size(max = 2000, message = "질문은 2000자 이하로 입력해 주세요.")
            String query) {
    }

    /**
     * 자격 판정 때만 받는 일시 정보. 기업정보 DB에 저장하지 않는다.
     * 신용점수·체납은 민감하고 자주 바뀌며, additionalFacts는 공고마다 다른 추가 사실(예: "최근 2개월 매출(원)")이다.
     */
    public record EligibilityRequest(
            @PositiveOrZero(message = "신용점수는 0 이상이어야 합니다.") @Max(value = 1000, message = "신용점수는 1000 이하입니다.")
            Integer creditScore,
            Boolean taxDelinquent,
            @Size(max = 20, message = "추가 정보는 20개까지 입력할 수 있습니다.") Map<String, Object> additionalFacts) {
    }

    /** FastAPI POST /internal/v1/eligibility 의 company_profile(CompanyProfileSnapshot)과 같은 이름·의미의 요청 본문. */
    @JsonInclude(JsonInclude.Include.NON_NULL)
    public record CompanyProfileSnapshot(
            @JsonProperty("company_name") String companyName,
            @JsonProperty("business_entity_type") String businessEntityType,
            @JsonProperty("company_size") String companySize,
            String region,
            String industry,
            @JsonProperty("business_start_date") LocalDate businessStartDate,
            @JsonProperty("business_status") String businessStatus,
            @JsonProperty("employee_count") Integer employeeCount,
            @JsonProperty("annual_revenue_krw") Long annualRevenueKrw,
            @JsonProperty("credit_score") Integer creditScore,
            @JsonProperty("tax_delinquent") Boolean taxDelinquent,
            @JsonProperty("venture_certified") Boolean ventureCertified,
            @JsonProperty("research_institute") Boolean researchInstitute,
            Boolean exporter,
            @JsonProperty("additional_facts") Map<String, Object> additionalFacts) {
    }

    public record EligibilityCommand(String pblancId, CompanyProfileSnapshot companyProfile) {
    }

    /** 공고문 근거 위치. location은 "p.3" 또는 HWPX section 이름처럼 사람이 읽는 위치다. */
    public record Citation(String evidenceId, String pblancId, String title, List<Integer> pages, String location,
                           List<String> headingPath) {
    }

    public record ProgramItem(String pblancId, String name, String category, String target, String jurisdictionName,
                              LocalDate applicationStartDate, LocalDate applicationEndDate, String applicationPeriodRaw) {
    }

    /** requestMode: SEARCH_LIST(공고 목록 찾기) 또는 DOCUMENT_QA(특정 공고 질문). */
    public record AiQueryResult(String requestMode, String status, String answer, List<ProgramItem> programs,
                                List<Citation> citations) {
    }

    /** 조건 하나의 판정. result는 MET(충족) / NOT_MET(미충족) / UNKNOWN(판단 불가)이다. */
    public record Criterion(String criterion, String result, String reason, List<Citation> citations) {
    }

    /** status: ELIGIBLE / INELIGIBLE / NEEDS_MORE_INFO / INSUFFICIENT_EVIDENCE (FastAPI가 계산한 값 그대로). */
    public record EligibilityResult(String pblancId, String programName, String status, List<Criterion> criteria,
                                    List<String> missingInformation, String disclaimer) {
    }
}
