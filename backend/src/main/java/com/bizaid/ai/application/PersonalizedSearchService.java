package com.bizaid.ai.application;

import com.bizaid.activity.application.ActivityLogService;
import com.bizaid.activity.domain.ActivityAction;
import com.bizaid.common.error.ApiException;
import com.bizaid.company.application.CompanyService;
import com.bizaid.company.domain.Company;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.stereotype.Service;

/**
 * V2 기업정보 기반 개인화 검색.
 * 흐름: 로그인 사용자 → 저장된 기업정보 조회(Spring 소유) → 검색에 필요한 값만 snapshot → AiGateway(FastAPI) → Top 3.
 * 기업정보 → 검색조건 변환은 FastAPI의 승인된 코드 매핑이 하고 LLM은 하지 않는다. Spring은 결과를 바꾸지 않는다.
 * V1 /api/ai/query(대화 저장 포함)와 의미가 달라 별도 유스케이스로 둔다. 이번 단계는 대화에 저장하지 않는다.
 */
@Service
public class PersonalizedSearchService {

    private final CompanyService companyService;
    private final AiGateway aiGateway;
    private final ActivityLogService activityLog;

    public PersonalizedSearchService(CompanyService companyService, AiGateway aiGateway, ActivityLogService activityLog) {
        this.companyService = companyService;
        this.aiGateway = aiGateway;
        this.activityLog = activityLog;
    }

    public AiDtos.PersonalizedSearchResult search(Long userId, String query) {
        // 기업정보가 없으면 개인화할 수 없으므로 company_not_registered(404)로 알린다.
        Company company = companyService.find(userId);
        AiDtos.CompanySearchSnapshot snapshot = new AiDtos.CompanySearchSnapshot(company.getCompanySize(),
                company.getBusinessStatus(), company.getRegion(), company.getBusinessStartDate());
        AiDtos.PersonalizedSearchResult result;
        try {
            result = aiGateway.personalizedSearch(new AiDtos.PersonalizedSearchCommand(query.strip(), snapshot));
        } catch (ApiException exception) {
            activityLog.failure(ActivityAction.AI_QUERY, userId, "COMPANY", company.getId(), exception.errorCode().code(),
                    Map.of("mode", "PERSONALIZED"));
            throw exception;
        }
        // 질문 본문·기업정보 값은 기록하지 않는다. 운영 확인용 결과 요약만 남긴다.
        Map<String, Object> metadata = new LinkedHashMap<>();
        metadata.put("mode", "PERSONALIZED");
        metadata.put("status", result.status());
        metadata.put("candidateCount", result.candidateCount());
        metadata.put("programCount", result.programs().size());
        activityLog.success(ActivityAction.AI_QUERY, userId, "COMPANY", company.getId(), metadata);
        return result;
    }
}
