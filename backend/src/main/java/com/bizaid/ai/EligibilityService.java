package com.bizaid.ai;

import com.bizaid.company.Company;
import com.bizaid.company.CompanyService;
import com.bizaid.program.ProgramService;
import java.util.Map;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 지원 자격 판정 요청 조립.
 * 로그인 사용자의 저장된 기업정보 + 이번 요청의 일시 정보 → CompanyProfileSnapshot → AiGateway.
 * 판정(조건별 충족 여부·최종 상태)은 FastAPI EligibilityService가 공고문 근거로 하며 Spring은 결과를 바꾸지 않는다.
 */
@Service
public class EligibilityService {

    private final CompanyService companyService;
    private final ProgramService programService;
    private final AiGateway aiGateway;

    public EligibilityService(CompanyService companyService, ProgramService programService, AiGateway aiGateway) {
        this.companyService = companyService;
        this.programService = programService;
        this.aiGateway = aiGateway;
    }

    // 트랜잭션은 DB 조회까지만 필요하다. 외부 AI 호출은 오래 걸릴 수 있어 연결 단계에서 조회와 호출을 분리할 예정이다.
    @Transactional(readOnly = true)
    public AiDtos.EligibilityResult evaluate(Long userId, String pblancId, AiDtos.EligibilityRequest request) {
        programService.findActive(pblancId);
        Company company = companyService.find(userId);
        return aiGateway.evaluateEligibility(new AiDtos.EligibilityCommand(pblancId, snapshot(company, request)));
    }

    static AiDtos.CompanyProfileSnapshot snapshot(Company company, AiDtos.EligibilityRequest request) {
        AiDtos.EligibilityRequest extra = request == null ? new AiDtos.EligibilityRequest(null, null, null) : request;
        Map<String, Object> facts = extra.additionalFacts() == null ? Map.of() : extra.additionalFacts();
        return new AiDtos.CompanyProfileSnapshot(company.getCompanyName(), company.getBusinessEntityType(),
                company.getCompanySize(), company.getRegion(), company.getIndustry(), company.getBusinessStartDate(),
                company.getBusinessStatus(), company.getEmployeeCount(), company.getAnnualRevenueKrw(), extra.creditScore(),
                extra.taxDelinquent(), company.getVentureCertified(), company.getResearchInstitute(), company.getExporter(), facts);
    }
}
