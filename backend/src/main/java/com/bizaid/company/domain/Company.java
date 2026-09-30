package com.bizaid.company.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.time.LocalDate;

/**
 * 사용자가 등록한 기업의 기본정보(사용자 1명당 1개).
 * 오래 유지되는 값만 저장한다. 신용점수·체납·공고별 추가 사실은 민감하거나 자주 바뀌므로 저장하지 않고
 * 자격 판정을 요청할 때만 받는다(ai.EligibilityService 참고).
 */
@Entity
@Table(name = "companies")
public class Company {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "user_id", nullable = false, unique = true)
    private Long userId;

    @Column(name = "company_name", nullable = false)
    private String companyName;

    @Column(name = "business_entity_type")
    private String businessEntityType;

    @Column(name = "company_size")
    private String companySize;

    private String region;

    private String industry;

    @Column(name = "business_start_date")
    private LocalDate businessStartDate;

    @Column(name = "business_status")
    private String businessStatus;

    @Column(name = "employee_count")
    private Integer employeeCount;

    @Column(name = "annual_revenue_krw")
    private Long annualRevenueKrw;

    @Column(name = "venture_certified")
    private Boolean ventureCertified;

    @Column(name = "research_institute")
    private Boolean researchInstitute;

    private Boolean exporter;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    protected Company() {
    }

    public Company(Long userId, CompanyDetails request, Instant now) {
        this.userId = userId;
        this.createdAt = now;
        apply(request, now);
    }

    /** 등록과 수정이 같은 입력 규칙을 쓰도록 값 반영을 한 곳에 둔다. 수정은 전체 교체(PUT)다. */
    public void apply(CompanyDetails request, Instant now) {
        this.companyName = request.companyName().trim();
        this.businessEntityType = request.businessEntityType();
        this.companySize = blankToNull(request.companySize());
        this.region = blankToNull(request.region());
        this.industry = blankToNull(request.industry());
        this.businessStartDate = request.businessStartDate();
        this.businessStatus = request.businessStatus();
        this.employeeCount = request.employeeCount();
        this.annualRevenueKrw = request.annualRevenueKrw();
        this.ventureCertified = request.ventureCertified();
        this.researchInstitute = request.researchInstitute();
        this.exporter = request.exporter();
        this.updatedAt = now;
    }

    private static String blankToNull(String value) {
        return value == null || value.isBlank() ? null : value.trim();
    }

    public Long getId() {
        return id;
    }

    public Long getUserId() {
        return userId;
    }

    public String getCompanyName() {
        return companyName;
    }

    public String getBusinessEntityType() {
        return businessEntityType;
    }

    public String getCompanySize() {
        return companySize;
    }

    public String getRegion() {
        return region;
    }

    public String getIndustry() {
        return industry;
    }

    public LocalDate getBusinessStartDate() {
        return businessStartDate;
    }

    public String getBusinessStatus() {
        return businessStatus;
    }

    public Integer getEmployeeCount() {
        return employeeCount;
    }

    public Long getAnnualRevenueKrw() {
        return annualRevenueKrw;
    }

    public Boolean getVentureCertified() {
        return ventureCertified;
    }

    public Boolean getResearchInstitute() {
        return researchInstitute;
    }

    public Boolean getExporter() {
        return exporter;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }
}
