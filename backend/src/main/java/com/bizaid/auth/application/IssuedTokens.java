package com.bizaid.auth.application;

import com.bizaid.auth.domain.User;

/** 로그인·가입·재발급 결과. refreshToken 원문은 Controller가 HttpOnly Cookie로만 내려보내고 응답 본문에는 넣지 않는다. */
public record IssuedTokens(User user, String accessToken, long expiresIn, String refreshToken) {
}
