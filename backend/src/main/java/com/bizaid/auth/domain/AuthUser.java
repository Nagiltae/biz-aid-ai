package com.bizaid.auth.domain;

/** JWT에서 꺼낸 현재 로그인 사용자. Controller는 @AuthenticationPrincipal로 받아 사용자 id만 서비스에 넘긴다. */
public record AuthUser(Long id, String email) {
}
