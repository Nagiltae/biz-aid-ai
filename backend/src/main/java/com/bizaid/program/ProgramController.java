package com.bizaid.program;

import com.bizaid.common.PageResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** 지원사업 목록·상세 API. 공개 공고 데이터라 로그인 없이 조회할 수 있다. */
@RestController
@RequestMapping("/api/programs")
public class ProgramController {

    private final ProgramService programService;

    public ProgramController(ProgramService programService) {
        this.programService = programService;
    }

    @GetMapping
    public PageResponse<ProgramDtos.ProgramSummary> search(@RequestParam(required = false) String keyword,
                                                           @RequestParam(required = false) String category,
                                                           @RequestParam(required = false) String target,
                                                           @RequestParam(required = false) String jurisdiction,
                                                           @RequestParam(required = false) RecruitmentStatus status,
                                                           @RequestParam(defaultValue = "0") int page,
                                                           @RequestParam(defaultValue = "20") int size) {
        return programService.search(new ProgramSearchCondition(keyword, category, target, jurisdiction, status), page, size);
    }

    @GetMapping("/filter-options")
    public ProgramDtos.FilterOptions filterOptions() {
        return programService.filterOptions();
    }

    @GetMapping("/{pblancId}")
    public ProgramDtos.ProgramDetail get(@PathVariable String pblancId) {
        return programService.get(pblancId);
    }
}
