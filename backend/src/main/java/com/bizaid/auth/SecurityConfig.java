package com.bizaid.auth;

import com.bizaid.common.ErrorCode;
import com.bizaid.common.ErrorResponse;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

/**
 * Spring Security 설정.
 * - 세션을 만들지 않는다(STATELESS). 로그인 상태는 요청마다 Access Token으로 확인한다.
 * - CSRF 토큰을 쓰지 않는다. 보호 API는 JS가 붙이는 Authorization 헤더로만 인증되어 다른 사이트가 위조할 수 없고,
 *   쿠키로 인증되는 /api/auth(재발급·로그아웃)는 Refresh Cookie의 SameSite=Strict와 좁은 Path로 막는다.
 * - React는 Vite proxy / nginx로 같은 origin처럼 호출하므로 CORS를 열지 않는다.
 * - 지원사업 조회는 공개 공고 데이터라 로그인 없이 허용하고, 기업정보·대화·AI 요청은 로그인이 필요하다.
 */
@Configuration
public class SecurityConfig {

    @Bean
    public SecurityFilterChain securityFilterChain(HttpSecurity http, JwtTokenProvider tokenProvider, ObjectMapper objectMapper)
            throws Exception {
        http.csrf(csrf -> csrf.disable())
                .cors(cors -> cors.disable())
                .httpBasic(basic -> basic.disable())
                .formLogin(form -> form.disable())
                .logout(logout -> logout.disable())
                .sessionManagement(session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.POST, "/api/auth/signup", "/api/auth/login", "/api/auth/refresh",
                                "/api/auth/logout").permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/programs", "/api/programs/filter-options",
                                "/api/programs/{pblancId}").permitAll()
                        .requestMatchers("/error").permitAll()
                        .anyRequest().authenticated())
                .exceptionHandling(handling -> handling.authenticationEntryPoint((request, response, exception) -> {
                    response.setStatus(ErrorCode.AUTH_REQUIRED.status().value());
                    response.setContentType(MediaType.APPLICATION_JSON_VALUE);
                    response.setCharacterEncoding("UTF-8");
                    objectMapper.writeValue(response.getWriter(), ErrorResponse.of(ErrorCode.AUTH_REQUIRED));
                }))
                .addFilterBefore(new JwtAuthenticationFilter(tokenProvider), UsernamePasswordAuthenticationFilter.class);
        return http.build();
    }

    /** 검증된 Spring Security 기본 인코더(BCrypt, {bcrypt} 접두어 포함)로 비밀번호를 해시한다. */
    @Bean
    public PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }
}
