package com.bizaid.company;

import com.bizaid.common.ApiException;
import com.bizaid.common.ErrorCode;
import java.time.Clock;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 로그인 사용자 본인의 기업정보 등록·조회·수정. 다른 사용자의 기업정보에 접근하는 경로는 없다(항상 userId로 찾는다). */
@Service
public class CompanyService {

    private final CompanyRepository companies;
    private final Clock clock;

    public CompanyService(CompanyRepository companies, Clock clock) {
        this.companies = companies;
        this.clock = clock;
    }

    @Transactional(readOnly = true)
    public CompanyResponse get(Long userId) {
        return CompanyResponse.from(find(userId));
    }

    /** 다른 기능(자격 판정)이 기업정보를 읽을 때 쓰는 진입점. 엔티티는 같은 트랜잭션 안에서만 쓴다. */
    @Transactional(readOnly = true)
    public Company find(Long userId) {
        return companies.findByUserId(userId).orElseThrow(() -> new ApiException(ErrorCode.COMPANY_NOT_REGISTERED));
    }

    @Transactional
    public CompanyResponse create(Long userId, CompanyRequest request) {
        if (companies.existsByUserId(userId)) {
            throw new ApiException(ErrorCode.COMPANY_ALREADY_REGISTERED);
        }
        try {
            return CompanyResponse.from(companies.saveAndFlush(new Company(userId, request, clock.instant())));
        } catch (DataIntegrityViolationException exception) {
            // 같은 사용자의 동시 등록은 DB UNIQUE(user_id)가 최종으로 막는다.
            throw new ApiException(ErrorCode.COMPANY_ALREADY_REGISTERED);
        }
    }

    @Transactional
    public CompanyResponse update(Long userId, CompanyRequest request) {
        Company company = find(userId);
        company.apply(request, clock.instant());
        return CompanyResponse.from(company);
    }
}
