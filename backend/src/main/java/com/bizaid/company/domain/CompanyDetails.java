package com.bizaid.company.domain;

import java.time.LocalDate;

/** 기업정보 등록·수정에 쓰는 값 묶음. HTTP 요청 형식과 분리해 도메인 모델이 presentation DTO에 의존하지 않게 한다. */
public record CompanyDetails(String companyName, String businessEntityType, String companySize, String region, String industry,
                             LocalDate businessStartDate, String businessStatus, Integer employeeCount, Long annualRevenueKrw,
                             Boolean ventureCertified, Boolean researchInstitute, Boolean exporter) {
}
