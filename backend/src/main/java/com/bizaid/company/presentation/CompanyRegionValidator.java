package com.bizaid.company.presentation;

import com.bizaid.company.infrastructure.RegionCatalog;
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

/** 계약에서 읽은 표준명 목록으로 기업 지역을 검사한다. 자유 입력(예: "경기도 광명시")은 받지 않는다. */
public class CompanyRegionValidator implements ConstraintValidator<CompanyRegion, String> {

    private final RegionCatalog catalog;

    public CompanyRegionValidator(RegionCatalog catalog) {
        this.catalog = catalog;
    }

    @Override
    public boolean isValid(String value, ConstraintValidatorContext context) {
        return value == null || catalog.contains(value);
    }
}
