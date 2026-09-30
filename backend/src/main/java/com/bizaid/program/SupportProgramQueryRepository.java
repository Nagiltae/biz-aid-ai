package com.bizaid.program;

import java.time.LocalDate;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

public interface SupportProgramQueryRepository {

    Page<SupportProgram> search(ProgramSearchCondition condition, LocalDate today, Pageable pageable);
}
