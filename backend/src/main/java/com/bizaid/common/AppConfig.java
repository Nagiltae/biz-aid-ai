package com.bizaid.common;

import com.querydsl.jpa.impl.JPAQueryFactory;
import jakarta.persistence.EntityManager;
import java.time.Clock;
import java.time.ZoneId;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** 여러 기능이 함께 쓰는 공통 Bean. */
@Configuration
public class AppConfig {

    /**
     * 신청기간은 한국 날짜로 적힌 값이므로 "오늘"과 모집 상태는 서비스 시간대(Asia/Seoul)로 계산한다.
     * DB에 저장하는 생성·수정 시각은 이와 별개로 UTC다. 테스트에서 날짜를 고정할 수 있게 Clock을 Bean으로 둔다.
     */
    @Bean
    public Clock clock(@Value("${bizaid.service-zone}") String zone) {
        return Clock.system(ZoneId.of(zone));
    }

    @Bean
    public JPAQueryFactory jpaQueryFactory(EntityManager entityManager) {
        return new JPAQueryFactory(entityManager);
    }
}
