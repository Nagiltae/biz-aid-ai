package com.bizaid.auth.infrastructure;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.List;
import org.springframework.http.HttpHeaders;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * Authorization: Bearer 헤더의 Access Token을 검증해 요청의 로그인 사용자를 정한다.
 * 토큰이 없거나 틀려도 여기서 응답하지 않는다. 보호된 API라면 Security가 401을 돌려주고,
 * React는 401을 받으면 Refresh API로 한 번 재발급을 시도한다.
 */
public class JwtAuthenticationFilter extends OncePerRequestFilter {

    private static final String PREFIX = "Bearer ";
    private final JwtTokenProvider tokenProvider;
    private final UserRepository users;

    public JwtAuthenticationFilter(JwtTokenProvider tokenProvider, UserRepository users) {
        this.tokenProvider = tokenProvider;
        this.users = users;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        String header = request.getHeader(HttpHeaders.AUTHORIZATION);
        if (header != null && header.startsWith(PREFIX)) {
            // BOUNDARY: 서명이 맞아도 탈퇴한 사용자의 토큰은 인증하지 않는다(Access Token은 서버에 저장하지 않아 사용자 행으로 확인).
            tokenProvider.parse(header.substring(PREFIX.length())).filter(user -> users.existsById(user.id())).ifPresent(user ->
                    SecurityContextHolder.getContext().setAuthentication(
                            new UsernamePasswordAuthenticationToken(user, null, List.of())));
        }
        chain.doFilter(request, response);
    }
}
