package com.bizaid.common.config;

import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.security.SecurityRequirement;
import io.swagger.v3.oas.models.security.SecurityScheme;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** API 문서(Swagger UI) 기본 정보. 보호 API는 Authorization: Bearer Access Token으로 시험한다(문서는 dev profile에서만 열림). */
@Configuration
public class OpenApiConfig {

    @Bean
    public OpenAPI bizAidOpenApi() {
        return new OpenAPI()
                .info(new Info().title("BizAid 서비스 API").version("v1")
                        .description("React가 호출하는 Spring API. AI 기능은 이 서버가 FastAPI 내부 API를 대신 호출한다."))
                .components(new Components().addSecuritySchemes("bearer",
                        new SecurityScheme().type(SecurityScheme.Type.HTTP).scheme("bearer").bearerFormat("JWT")))
                .addSecurityItem(new SecurityRequirement().addList("bearer"));
    }
}
