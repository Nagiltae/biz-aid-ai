package com.bizaid.company.application;

import com.bizaid.activity.application.ActivityLogService;
import com.bizaid.activity.domain.ActivityAction;
import com.bizaid.common.error.ApiException;
import com.bizaid.common.error.ErrorCode;
import com.bizaid.company.domain.Company;
import com.bizaid.company.domain.CompanyDetails;
import com.bizaid.company.infrastructure.CompanyRepository;
import java.time.Clock;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 로그인 사용자 본인의 기업정보 등록·조회·수정. 다른 사용자의 기업정보에 접근하는 경로는 없다(항상 userId로 찾는다). */
@Service
public class CompanyService {

    private final CompanyRepository companies;
    private final Clock clock;
    private final ActivityLogService activityLog;

    public CompanyService(CompanyRepository companies, Clock clock, ActivityLogService activityLog) {
        this.companies = companies;
        this.clock = clock;
        this.activityLog = activityLog;
    }

    @Transactional(readOnly = true)
    public CompanyResponse get(Long userId) {
        return CompanyResponse.from(find(userId));
    }

    /**
     * 기업정보가 있어야 쓰는 기능(AI 검색·대화)의 공통 확인. 없으면 company_not_registered로 막는다.
     * 화면도 같은 규칙으로 막지만, API를 직접 호출하는 우회를 서버에서 한 번 더 막는다.
     */
    @Transactional(readOnly = true)
    public void requireRegistered(Long userId) {
        if (!companies.existsByUserId(userId)) {
            throw new ApiException(ErrorCode.COMPANY_NOT_REGISTERED);
        }
    }

    /** 다른 기능(자격 판정)이 기업정보를 읽을 때 쓰는 진입점. 엔티티는 같은 트랜잭션 안에서만 쓴다. */
    @Transactional(readOnly = true)
    public Company find(Long userId) {
        return companies.findByUserId(userId).orElseThrow(() -> new ApiException(ErrorCode.COMPANY_NOT_REGISTERED));
    }

    @Transactional
    public CompanyResponse create(Long userId, CompanyDetails details) {
        if (companies.existsByUserId(userId)) {
            throw new ApiException(ErrorCode.COMPANY_ALREADY_REGISTERED);
        }
        Company company;
        try {
            company = companies.saveAndFlush(new Company(userId, details, clock.instant()));
        } catch (DataIntegrityViolationException exception) {
            // 같은 사용자의 동시 등록은 DB UNIQUE(user_id)가 최종으로 막는다.
            throw new ApiException(ErrorCode.COMPANY_ALREADY_REGISTERED);
        }
        // 기업정보 값 자체는 기록하지 않는다(기업정보의 기준 저장소는 companies다).
        activityLog.success(ActivityAction.COMPANY_CREATE, userId, "COMPANY", company.getId(), null);
        return CompanyResponse.from(company);
    }

    @Transactional
    public CompanyResponse update(Long userId, CompanyDetails details) {
        Company company = find(userId);
        company.apply(details, clock.instant());
        activityLog.success(ActivityAction.COMPANY_UPDATE, userId, "COMPANY", company.getId(), null);
        return CompanyResponse.from(company);
    }
}
