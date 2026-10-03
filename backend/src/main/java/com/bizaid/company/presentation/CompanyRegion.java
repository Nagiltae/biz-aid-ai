package com.bizaid.company.presentation;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/** 기업 지역은 공통 계약의 광역 지자체 표준명 중 하나여야 한다. 비우면(null) "지역 모름"이다. */
@Target({ElementType.FIELD, ElementType.RECORD_COMPONENT, ElementType.PARAMETER})
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = CompanyRegionValidator.class)
public @interface CompanyRegion {
    String message() default "지역은 목록의 광역 지자체 중에서 선택해 주세요.";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};
}
