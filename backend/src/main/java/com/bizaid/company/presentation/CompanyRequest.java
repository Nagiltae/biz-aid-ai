package com.bizaid.company.presentation;

import com.bizaid.company.domain.CompanyDetails;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.PastOrPresent;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.PositiveOrZero;
import jakarta.validation.constraints.Size;
import java.time.LocalDate;

/**
 * 기업정보 등록·수정 요청. 회사명 외에는 모두 선택이다.
 * 값이 없으면 자격 판정에서 해당 조건이 "판단 불가(UNKNOWN)"가 될 뿐 오류가 아니다.
 * 사업자 형태·영업 상태 허용값은 AI 계층 CompanyProfileSnapshot과 DB CHECK 제약과 같다.
 */
public record CompanyRequest(
        @NotBlank(message = "회사명을 입력해 주세요.") @Size(max = 100, message = "회사명은 100자 이하로 입력해 주세요.")
        String companyName,
        @Pattern(regexp = "개인사업자|법인", message = "사업자 형태는 개인사업자 또는 법인입니다.") String businessEntityType,
        // 맞춤 추천의 기업규모 → 지원대상 매핑과 같은 선택지만 받는다(비우면 "모름·해당 없음"). 기존 자유 입력 값은 다음 수정 때 다시 고른다.
        @Pattern(regexp = "소상공인|중소기업|중견기업", message = "기업 규모는 소상공인·중소기업·중견기업 중에서 선택해 주세요.") String companySize,
        @Size(max = 100, message = "지역은 100자 이하로 입력해 주세요.") String region,
        @Size(max = 100, message = "업종은 100자 이하로 입력해 주세요.") String industry,
        @PastOrPresent(message = "개업일은 오늘 이전 날짜여야 합니다.") LocalDate businessStartDate,
        @Pattern(regexp = "영업중|휴업|폐업", message = "영업 상태는 영업중·휴업·폐업 중 하나입니다.") String businessStatus,
        @PositiveOrZero(message = "직원 수는 0 이상이어야 합니다.") @Max(value = 10_000_000, message = "직원 수가 너무 큽니다.")
        Integer employeeCount,
        @PositiveOrZero(message = "연 매출은 0 이상이어야 합니다.") Long annualRevenueKrw,
        Boolean ventureCertified,
        Boolean researchInstitute,
        Boolean exporter) {

    CompanyDetails toDetails() {
        return new CompanyDetails(companyName, businessEntityType, companySize, region, industry, businessStartDate, businessStatus,
                employeeCount, annualRevenueKrw, ventureCertified, researchInstitute, exporter);
    }
}
