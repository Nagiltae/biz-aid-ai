package com.bizaid.program.infrastructure;

import static com.bizaid.program.domain.QSupportProgram.supportProgram;

import com.bizaid.program.domain.ProgramSearchCondition;
import com.bizaid.program.domain.RecruitmentStatus;
import com.bizaid.program.domain.SupportProgram;
import com.querydsl.core.BooleanBuilder;
import com.querydsl.core.types.dsl.BooleanExpression;
import com.querydsl.jpa.impl.JPAQueryFactory;
import java.time.LocalDate;
import java.util.List;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.Pageable;

/**
 * 지원사업 목록 검색. 검색어·지원분야·지원대상·소관기관·모집 상태가 어떤 조합으로든 들어올 수 있으므로
 * 문자열 SQL을 이어 붙이는 대신 QueryDSL로 값이 있는 조건만 타입 안전하게 추가한다.
 * AI 검색이 아니라 MySQL에 저장된 정확한 값으로 거르는 일반 검색이다.
 */
public class SupportProgramQueryRepositoryImpl implements SupportProgramQueryRepository {

    private final JPAQueryFactory queryFactory;

    public SupportProgramQueryRepositoryImpl(JPAQueryFactory queryFactory) {
        this.queryFactory = queryFactory;
    }

    @Override
    public Page<SupportProgram> search(ProgramSearchCondition condition, LocalDate today, Pageable pageable) {
        BooleanBuilder where = new BooleanBuilder()
                // BOUNDARY: 서비스에는 현재 기업마당에 살아 있는 공고만 보여 준다(파이프라인 lifecycle 그대로).
                .and(supportProgram.sourceActive.isTrue())
                .and(supportProgram.sourceDeleted.isFalse())
                .and(keyword(condition.keyword()))
                .and(equalsIfPresent(supportProgram.category, condition.category()))
                .and(equalsIfPresent(supportProgram.target, condition.target()))
                .and(equalsIfPresent(supportProgram.jurisdictionName, condition.jurisdiction()))
                .and(status(condition.status(), today));
        List<SupportProgram> content = queryFactory.selectFrom(supportProgram)
                .where(where)
                // 공고 ID가 클수록 최근 등록 공고다. 같은 조건이면 순서가 항상 같도록 유일 key로 정렬한다.
                .orderBy(supportProgram.pblancId.desc())
                .offset(pageable.getOffset())
                .limit(pageable.getPageSize())
                .fetch();
        Long total = queryFactory.select(supportProgram.count()).from(supportProgram).where(where).fetchOne();
        return new PageImpl<>(content, pageable, total == null ? 0 : total);
    }

    // 검색어는 공고명과 기업마당 해시태그(지역·업종 키워드 포함)에서 찾는다. 요약 HTML 본문은 태그가 섞여 있어 제외한다.
    private static BooleanExpression keyword(String keyword) {
        if (keyword == null || keyword.isBlank()) {
            return null;
        }
        String value = keyword.trim();
        return supportProgram.name.contains(value).or(supportProgram.hashtagsRaw.contains(value));
    }

    private static BooleanExpression equalsIfPresent(com.querydsl.core.types.dsl.StringPath path, String value) {
        return value == null || value.isBlank() ? null : path.eq(value.trim());
    }

    /** RecruitmentStatus.of와 같은 규칙을 SQL 조건으로 옮긴 것이다. 두 곳의 규칙이 어긋나지 않도록 테스트로 확인한다. */
    private static BooleanExpression status(RecruitmentStatus status, LocalDate today) {
        if (status == null) {
            return null;
        }
        var start = supportProgram.applicationStartDate;
        var end = supportProgram.applicationEndDate;
        BooleanExpression dated = start.isNotNull().or(end.isNotNull());
        return switch (status) {
            case UNDATED -> start.isNull().and(end.isNull());
            case CLOSED -> end.isNotNull().and(end.lt(today));
            case UPCOMING -> dated.and(end.isNull().or(end.goe(today))).and(start.isNotNull().and(start.gt(today)));
            case OPEN -> dated.and(end.isNull().or(end.goe(today))).and(start.isNull().or(start.loe(today)));
        };
    }
}
