package com.bizaid.ai.application;

import com.bizaid.activity.application.ActivityLogService;
import com.bizaid.activity.domain.ActivityAction;
import com.bizaid.common.error.ApiException;
import com.bizaid.company.application.CompanyService;
import com.bizaid.company.domain.Company;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.TreeMap;
import org.springframework.stereotype.Service;

/**
 * V2 Top 3 자격 판정: 로그인 사용자의 저장된 기업정보 → 판정용 snapshot(V1 단일 판정과 같은 매핑) → FastAPI 한 번 호출.
 * 검색 Top 3와 공고별 판정의 조합은 FastAPI가 한다. React가 공고를 하나씩 돌며 AI 흐름을 소유하지 않게 하기 위해서다.
 * 저장되지 않은 값(신용점수·체납·추가 사실)은 만들지 않고 비워 보낸다. 판정은 그 조건을 판단 불가(NEEDS_MORE_INFO)로 남긴다.
 */
@Service
public class PersonalizedEligibilityService {

    private final CompanyService companyService;
    private final AiGateway aiGateway;
    private final ActivityLogService activityLog;

    public PersonalizedEligibilityService(CompanyService companyService, AiGateway aiGateway, ActivityLogService activityLog) {
        this.companyService = companyService;
        this.aiGateway = aiGateway;
        this.activityLog = activityLog;
    }

    public AiDtos.PersonalizedEligibilityResult evaluate(Long userId, String query) {
        Company company = companyService.find(userId);
        AiDtos.CompanyProfileSnapshot snapshot = EligibilityService.snapshot(company, null);
        AiDtos.PersonalizedEligibilityResult result;
        try {
            result = aiGateway.personalizedEligibility(new AiDtos.PersonalizedEligibilityCommand(query.strip(), snapshot));
        } catch (ApiException exception) {
            activityLog.failure(ActivityAction.ELIGIBILITY_CHECK, userId, "COMPANY", company.getId(), exception.errorCode().code(),
                    Map.of("mode", "PERSONALIZED_TOP3"));
            throw exception;
        }
        // 상태별 개수만 기록한다(질문·기업정보·판정 근거 본문은 넣지 않는다).
        Map<String, Integer> outcomes = new TreeMap<>();
        for (AiDtos.ProgramEvaluation evaluation : result.evaluations()) {
            String key = "COMPLETED".equals(evaluation.evaluationStatus()) ? evaluation.eligibility().status() : "FAILED";
            outcomes.merge(key, 1, Integer::sum);
        }
        Map<String, Object> metadata = new LinkedHashMap<>();
        metadata.put("mode", "PERSONALIZED_TOP3");
        metadata.put("searchStatus", result.search().status());
        metadata.put("outcomes", outcomes);
        activityLog.success(ActivityAction.ELIGIBILITY_CHECK, userId, "COMPANY", company.getId(), metadata);
        return result;
    }
}
