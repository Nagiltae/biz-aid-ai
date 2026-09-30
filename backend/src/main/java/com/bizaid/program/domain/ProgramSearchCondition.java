package com.bizaid.program.domain;

/**
 * 지원사업 목록 검색 조건. 모든 값은 선택이며 비어 있으면 그 조건을 적용하지 않는다.
 * category·target·jurisdiction은 support_programs에 실제로 저장된 값과 정확히 일치해야 한다(선택지는 filter-options API가 준다).
 */
public record ProgramSearchCondition(String keyword, String category, String target, String jurisdiction,
                                     RecruitmentStatus status) {
}
