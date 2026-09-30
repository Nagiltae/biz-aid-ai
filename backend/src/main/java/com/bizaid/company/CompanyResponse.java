package com.bizaid.company;

import java.time.Instant;
import java.time.LocalDate;

public record CompanyResponse(Long id, String companyName, String businessEntityType, String companySize, String region,
                              String industry, LocalDate businessStartDate, String businessStatus, Integer employeeCount,
                              Long annualRevenueKrw, Boolean ventureCertified, Boolean researchInstitute, Boolean exporter,
                              Instant updatedAt) {

    static CompanyResponse from(Company company) {
        return new CompanyResponse(company.getId(), company.getCompanyName(), company.getBusinessEntityType(),
                company.getCompanySize(), company.getRegion(), company.getIndustry(), company.getBusinessStartDate(),
                company.getBusinessStatus(), company.getEmployeeCount(), company.getAnnualRevenueKrw(),
                company.getVentureCertified(), company.getResearchInstitute(), company.getExporter(), company.getUpdatedAt());
    }
}
