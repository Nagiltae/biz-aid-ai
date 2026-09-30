package com.bizaid;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

/**
 * BizAid 서비스 서버.
 * 회원·기업정보·대화 같은 서비스 데이터의 기준 시스템이며, React는 이 서버만 호출한다.
 * AI 기능(검색·자격 판정)은 이후 단계에서 FastAPI 내부 API를 호출하도록 ai 패키지의 AiGateway 뒤에 연결한다.
 */
@SpringBootApplication
@ConfigurationPropertiesScan
public class BizAidApplication {

    public static void main(String[] args) {
        SpringApplication.run(BizAidApplication.class, args);
    }
}
