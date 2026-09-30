package com.bizaid;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.bizaid.program.ProgramSearchCondition;
import com.bizaid.program.RecruitmentStatus;
import com.bizaid.program.SupportProgram;
import com.bizaid.program.SupportProgramRepository;
import java.time.LocalDate;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.domain.PageRequest;
import org.springframework.jdbc.core.JdbcTemplate;

/** QueryDSL 동적 조건 검색과 모집 상태 규칙(SQL 조건 = RecruitmentStatus.of)이 일치하는지 확인한다. */
@SpringBootTest
@AutoConfigureMockMvc
class ProgramSearchTest extends ApiTestSupport {

    static final LocalDate TODAY = LocalDate.of(2026, 10, 1);

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    SupportProgramRepository programs;

    @BeforeEach
    void seed() {
        jdbc.update("DELETE FROM support_programs");
        insert(1, "PBLN_1", "소상공인 경영안정자금", "금융", "소상공인", "경기도", "2026-09-01", "2026-10-31", true, "<p>요약<br>둘째 줄</p><script>x</script>");
        insert(2, "PBLN_2", "수출 바우처", "수출", "중소기업", "산업통상부", "2026-11-01", "2026-11-30", true, null);
        insert(3, "PBLN_3", "지난 금융 공고", "금융", "중소기업", "경기도", "2026-08-01", "2026-09-30", true, null);
        insert(4, "PBLN_4", "상시 금융 보증", "금융", "소상공인", "부산광역시", null, null, true, null);
        insert(5, "PBLN_5", "삭제된 금융 공고", "금융", "소상공인", "경기도", null, null, false, null);
    }

    private void insert(long id, String pblancId, String name, String category, String target, String jurisdiction,
                        String start, String end, boolean active, String summary) {
        jdbc.update("INSERT INTO support_programs (id, pblanc_id, name, category, target, jurisdiction_name, application_start_date,"
                        + " application_end_date, source_active, source_deleted, summary_html) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                id, pblancId, name, category, target, jurisdiction, start == null ? null : LocalDate.parse(start),
                end == null ? null : LocalDate.parse(end), active, !active, summary);
    }

    private List<String> ids(ProgramSearchCondition condition) {
        return programs.search(condition, TODAY, PageRequest.of(0, 20)).map(SupportProgram::getPblancId).getContent();
    }

    @Test
    void conditionsCombineAndInactiveProgramsAreHidden() {
        assertThat(ids(new ProgramSearchCondition(null, null, null, null, null))).containsExactly("PBLN_4", "PBLN_3", "PBLN_2", "PBLN_1");
        assertThat(ids(new ProgramSearchCondition(null, "금융", "소상공인", null, null))).containsExactly("PBLN_4", "PBLN_1");
        assertThat(ids(new ProgramSearchCondition("금융", null, null, "경기도", null))).containsExactly("PBLN_3");
        assertThat(ids(new ProgramSearchCondition("경영안정", "금융", null, null, RecruitmentStatus.OPEN))).containsExactly("PBLN_1");
    }

    @Test
    void recruitmentStatusFilterMatchesStatusRule() {
        for (RecruitmentStatus status : RecruitmentStatus.values()) {
            List<SupportProgram> found = programs.search(new ProgramSearchCondition(null, null, null, null, status), TODAY,
                    PageRequest.of(0, 20)).getContent();
            assertThat(found).isNotEmpty().allMatch(program -> program.recruitmentStatus(TODAY) == status);
        }
    }

    @Test
    void detailApiReturnsPlainTextSummaryAndHidesInactivePrograms() throws Exception {
        mvc.perform(get("/api/programs/PBLN_1")).andExpect(status().isOk())
                .andExpect(jsonPath("$.summary").value("요약\n둘째 줄"))
                .andExpect(jsonPath("$.category").value("금융"));
        mvc.perform(get("/api/programs/PBLN_5")).andExpect(status().isNotFound())
                .andExpect(jsonPath("$.error.code").value("program_not_found"));
        mvc.perform(get("/api/programs").param("category", "금융").param("size", "1")).andExpect(status().isOk())
                .andExpect(jsonPath("$.totalElements").value(3)).andExpect(jsonPath("$.items.length()").value(1));
    }
}
