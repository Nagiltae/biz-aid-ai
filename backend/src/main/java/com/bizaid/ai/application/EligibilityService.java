package com.bizaid.ai.application;

import com.bizaid.activity.application.ActivityLogService;
import com.bizaid.activity.domain.ActivityAction;
import com.bizaid.common.error.ApiException;
import com.bizaid.common.error.ErrorCode;
import com.bizaid.company.application.CompanyService;
import com.bizaid.company.domain.Company;
import com.bizaid.program.application.ProgramService;
import java.util.Map;
import org.springframework.stereotype.Service;

/**
 * 지원 자격 판정 요청 조립.
 * 로그인 사용자의 저장된 기업정보 + 이번 요청의 일시 정보 → CompanyProfileSnapshot → AiGateway(FastAPI).
 * 판정(조건별 충족 여부·최종 상태·근거)은 FastAPI EligibilityService가 공고문 근거로 하며 Spring은 결과를 바꾸지 않는다.
 * 트랜잭션은 조회 메서드 안에서만 쓰고, 수십 초 걸리는 AI 호출 동안에는 DB 연결을 잡지 않는다.
 */
@Service
public class EligibilityService {

    private final CompanyService companyService;
    private final ProgramService programService;
    private final AiGateway aiGateway;
    private final ActivityLogService activityLog;

    public EligibilityService(CompanyService companyService, ProgramService programService, AiGateway aiGateway,
                              ActivityLogService activityLog) {
        this.companyService = companyService;
        this.programService = programService;
        this.aiGateway = aiGateway;
        this.activityLog = activityLog;
    }

    public AiDtos.EligibilityResult evaluate(Long userId, String pblancId, AiDtos.TemporaryFacts facts) {
        try {
            programService.findActive(pblancId);
            Company company = companyService.find(userId);
            AiDtos.EligibilityResult result = aiGateway.evaluateEligibility(
                    new AiDtos.EligibilityCommand(pblancId, snapshot(company, facts)));
            // 판정 상태만 남긴다. 기업정보·신용점수 같은 입력값은 활동 기록에 넣지 않는다.
            activityLog.success(ActivityAction.ELIGIBILITY_CHECK, userId, "PROGRAM", pblancId, Map.of("status", result.status()));
            return result;
        } catch (ApiException exception) {
            activityLog.failure(ActivityAction.ELIGIBILITY_CHECK, userId, "PROGRAM", pblancId, exception.errorCode().code(), null);
            throw exception;
        }
    }

    static AiDtos.CompanyProfileSnapshot snapshot(Company company, AiDtos.TemporaryFacts request) {
        AiDtos.TemporaryFacts extra = request == null ? new AiDtos.TemporaryFacts(null, null, null) : request;
        Map<String, Object> facts = extra.additionalFacts() == null ? Map.of() : extra.additionalFacts();
        // FastAPI Snapshot은 추가 사실 값으로 문자·숫자·참거짓만 받는다. 형식이 틀린 값은 AI 호출 전에 입력 오류로 돌려준다.
        boolean valid = facts.entrySet().stream().allMatch(entry -> entry.getKey() != null && !entry.getKey().isBlank()
                && (entry.getValue() instanceof String || entry.getValue() instanceof Number || entry.getValue() instanceof Boolean));
        if (!valid) {
            throw new ApiException(ErrorCode.VALIDATION_FAILED);
        }
        return new AiDtos.CompanyProfileSnapshot(company.getCompanyName(), company.getBusinessEntityType(),
                company.getCompanySize(), company.getRegion(), company.getIndustry(), company.getBusinessStartDate(),
                company.getBusinessStatus(), company.getEmployeeCount(), company.getAnnualRevenueKrw(), extra.creditScore(),
                extra.taxDelinquent(), company.getVentureCertified(), company.getResearchInstitute(), company.getExporter(), facts);
    }
}
