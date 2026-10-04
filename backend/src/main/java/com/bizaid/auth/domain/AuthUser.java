package com.bizaid.auth.domain;

import com.bizaid.common.error.ApiException;
import com.bizaid.common.error.ErrorCode;

/**
 * JWT에서 꺼낸 현재 로그인 사용자. Controller는 @AuthenticationPrincipal로 받아 사용자 id만 서비스에 넘긴다.
 * trial은 토큰 발급 때 계정 종류로 정한다. 계정 종류는 바뀌지 않으므로 요청마다 DB를 다시 보지 않는다.
 */
public record AuthUser(Long id, String email, boolean trial) {

    public AuthUser(Long id, String email) {
        this(id, email, false);
    }

    /** 체험 계정이 쓸 수 없는 기능(기업정보 수정·비밀번호 변경·탈퇴)의 입구에서 부른다. */
    public void requireMember() {
        if (trial) {
            throw new ApiException(ErrorCode.TRIAL_ACCOUNT_RESTRICTED);
        }
    }
}
