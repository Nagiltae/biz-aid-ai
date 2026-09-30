package com.bizaid.program;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.LocalDate;
import org.hibernate.annotations.Immutable;

/**
 * 데이터 파이프라인이 적재한 기존 support_programs 테이블의 조회 전용 매핑.
 * BOUNDARY: schema 소유자는 데이터 파이프라인(공통 Flyway V1)이다. Spring은 새 테이블로 복제하지 않고
 * 화면에 필요한 column만 읽는다. @Immutable이라 Hibernate가 UPDATE를 만들지 않으며 저장 API도 없다.
 * *_raw column은 기업마당 원문 그대로이고, 신청 시작·종료일은 원문이 날짜 범위일 때만 파이프라인이 채운 파생값이다.
 */
@Entity
@Immutable
@Table(name = "support_programs")
public class SupportProgram {

    @Id
    private Long id;

    @Column(name = "pblanc_id")
    private String pblancId;

    private String name;

    private String category;

    private String target;

    @Column(name = "jurisdiction_name")
    private String jurisdictionName;

    @Column(name = "executing_org_name")
    private String executingOrgName;

    @Column(name = "summary_html")
    private String summaryHtml;

    @Column(name = "application_period_raw")
    private String applicationPeriodRaw;

    @Column(name = "application_start_date")
    private LocalDate applicationStartDate;

    @Column(name = "application_end_date")
    private LocalDate applicationEndDate;

    @Column(name = "application_method_raw")
    private String applicationMethodRaw;

    @Column(name = "application_url_raw")
    private String applicationUrlRaw;

    @Column(name = "announcement_url")
    private String announcementUrl;

    @Column(name = "hashtags_raw")
    private String hashtagsRaw;

    @Column(name = "source_active")
    private boolean sourceActive;

    @Column(name = "source_deleted")
    private boolean sourceDeleted;

    protected SupportProgram() {
    }

    public RecruitmentStatus recruitmentStatus(LocalDate today) {
        return RecruitmentStatus.of(applicationStartDate, applicationEndDate, today);
    }

    public Long getId() {
        return id;
    }

    public String getPblancId() {
        return pblancId;
    }

    public String getName() {
        return name;
    }

    public String getCategory() {
        return category;
    }

    public String getTarget() {
        return target;
    }

    public String getJurisdictionName() {
        return jurisdictionName;
    }

    public String getExecutingOrgName() {
        return executingOrgName;
    }

    public String getSummaryHtml() {
        return summaryHtml;
    }

    public String getApplicationPeriodRaw() {
        return applicationPeriodRaw;
    }

    public LocalDate getApplicationStartDate() {
        return applicationStartDate;
    }

    public LocalDate getApplicationEndDate() {
        return applicationEndDate;
    }

    public String getApplicationMethodRaw() {
        return applicationMethodRaw;
    }

    public String getApplicationUrlRaw() {
        return applicationUrlRaw;
    }

    public String getAnnouncementUrl() {
        return announcementUrl;
    }

    public String getHashtagsRaw() {
        return hashtagsRaw;
    }
}
