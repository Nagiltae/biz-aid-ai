package com.bizaid.program.domain;

import java.time.LocalDate;

/**
 * 파생 신청기간(시작·종료일)과 오늘 날짜로 계산한 모집 상태.
 * WHY: "예산 소진시까지"·"상시 접수"처럼 날짜가 없는 원문은 마감 여부를 판정할 수 없으므로 마감으로 추측하지 않고
 * UNDATED로 따로 둔다. 이 규칙은 AI 후보 선택(candidates/service.py)의 신청기간 조건과 같다.
 */
public enum RecruitmentStatus {
    OPEN("접수중"),
    UPCOMING("접수 예정"),
    CLOSED("마감"),
    UNDATED("상시·기간 미정");

    private final String label;

    RecruitmentStatus(String label) {
        this.label = label;
    }

    public String label() {
        return label;
    }

    public static RecruitmentStatus of(LocalDate start, LocalDate end, LocalDate today) {
        if (start == null && end == null) {
            return UNDATED;
        }
        if (end != null && end.isBefore(today)) {
            return CLOSED;
        }
        if (start != null && start.isAfter(today)) {
            return UPCOMING;
        }
        return OPEN;
    }
}
