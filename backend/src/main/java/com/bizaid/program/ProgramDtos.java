package com.bizaid.program;

import java.time.LocalDate;
import java.util.List;

/** 지원사업 API 응답 DTO. 없는 값은 null로 두고 원문에서 새 정보를 추론하지 않는다. */
public final class ProgramDtos {

    private ProgramDtos() {
    }

    public record ProgramSummary(String pblancId, String name, String category, String target, String jurisdictionName,
                                 LocalDate applicationStartDate, LocalDate applicationEndDate, String applicationPeriodRaw,
                                 RecruitmentStatus recruitmentStatus, String recruitmentStatusLabel) {

        static ProgramSummary from(SupportProgram program, LocalDate today) {
            RecruitmentStatus status = program.recruitmentStatus(today);
            return new ProgramSummary(program.getPblancId(), program.getName(), program.getCategory(), program.getTarget(),
                    program.getJurisdictionName(), program.getApplicationStartDate(), program.getApplicationEndDate(),
                    program.getApplicationPeriodRaw(), status, status.label());
        }
    }

    /** summary는 HTML을 제거한 텍스트, applicationUrl·applicationMethod는 기업마당 원문 값이다. */
    public record ProgramDetail(String pblancId, String name, String category, String target, String jurisdictionName,
                                String executingOrgName, LocalDate applicationStartDate, LocalDate applicationEndDate,
                                String applicationPeriodRaw, RecruitmentStatus recruitmentStatus,
                                String recruitmentStatusLabel, String summary, String applicationMethod,
                                String announcementUrl, String applicationUrl) {

        static ProgramDetail from(SupportProgram program, LocalDate today) {
            RecruitmentStatus status = program.recruitmentStatus(today);
            return new ProgramDetail(program.getPblancId(), program.getName(), program.getCategory(), program.getTarget(),
                    program.getJurisdictionName(), program.getExecutingOrgName(), program.getApplicationStartDate(),
                    program.getApplicationEndDate(), program.getApplicationPeriodRaw(), status, status.label(),
                    HtmlText.toPlainText(program.getSummaryHtml()), program.getApplicationMethodRaw(),
                    program.getAnnouncementUrl(), program.getApplicationUrlRaw());
        }
    }

    public record StatusOption(RecruitmentStatus value, String label) {
    }

    public record FilterOptions(List<String> categories, List<String> targets, List<String> jurisdictions,
                                List<StatusOption> statuses) {
    }
}
