package com.bizaid.program.application;

import com.bizaid.common.error.ApiException;
import com.bizaid.common.error.ErrorCode;
import com.bizaid.common.web.PageResponse;
import com.bizaid.program.domain.ProgramSearchCondition;
import com.bizaid.program.domain.RecruitmentStatus;
import com.bizaid.program.domain.SupportProgram;
import com.bizaid.program.infrastructure.SupportProgramRepository;
import java.time.Clock;
import java.time.LocalDate;
import java.util.Arrays;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 지원사업 일반 조회(목록·상세·필터 선택지). 모든 값은 MySQL support_programs에서 읽기만 한다. */
@Service
@Transactional(readOnly = true)
public class ProgramService {

    static final int MAX_PAGE_SIZE = 50;

    private final SupportProgramRepository programs;
    private final Clock clock;

    public ProgramService(SupportProgramRepository programs, Clock clock) {
        this.programs = programs;
        this.clock = clock;
    }

    public PageResponse<ProgramDtos.ProgramSummary> search(ProgramSearchCondition condition, int page, int size) {
        LocalDate today = LocalDate.now(clock);
        // 과도한 한 번 조회를 막기 위해 페이지 크기를 제한한다.
        PageRequest pageable = PageRequest.of(Math.max(page, 0), Math.min(Math.max(size, 1), MAX_PAGE_SIZE));
        return PageResponse.from(programs.search(condition, today, pageable), program -> ProgramDtos.ProgramSummary.from(program, today));
    }

    public ProgramDtos.ProgramDetail get(String pblancId) {
        return ProgramDtos.ProgramDetail.from(findActive(pblancId), LocalDate.now(clock));
    }

    /** 자격 판정 등 다른 기능이 "지금 게시 중인 공고인지" 확인할 때 쓰는 진입점. */
    public SupportProgram findActive(String pblancId) {
        return programs.findByPblancIdAndSourceActiveTrueAndSourceDeletedFalse(pblancId)
                .orElseThrow(() -> new ApiException(ErrorCode.PROGRAM_NOT_FOUND));
    }

    public ProgramDtos.FilterOptions filterOptions() {
        return new ProgramDtos.FilterOptions(programs.findActiveCategories(), programs.findActiveTargets(),
                programs.findActiveJurisdictions(), Arrays.stream(RecruitmentStatus.values())
                .map(status -> new ProgramDtos.StatusOption(status, status.label())).toList());
    }
}
