package com.bizaid.auth;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

/** 인증 API 요청·응답 DTO. 엔티티를 응답으로 직접 내보내지 않도록 필요한 값만 담는다. */
public final class AuthDtos {

    private AuthDtos() {
    }

    // 비밀번호 정책은 길이 8~64자만 둔다. 복잡한 조합 규칙보다 길이가 실제 안전성에 더 기여하고 V1 사용성을 해치지 않는다.
    public record SignupRequest(
            @NotBlank(message = "이메일을 입력해 주세요.") @Email(message = "이메일 형식이 올바르지 않습니다.")
            @Size(max = 255, message = "이메일이 너무 깁니다.") String email,
            @NotBlank(message = "비밀번호를 입력해 주세요.") @Size(min = 8, max = 64, message = "비밀번호는 8~64자로 입력해 주세요.")
            String password,
            @NotBlank(message = "이름을 입력해 주세요.") @Size(max = 50, message = "이름은 50자 이하로 입력해 주세요.")
            String displayName) {
    }

    public record LoginRequest(
            @NotBlank(message = "이메일을 입력해 주세요.") String email,
            @NotBlank(message = "비밀번호를 입력해 주세요.") String password) {
    }

    public record UserResponse(Long id, String email, String displayName) {

        static UserResponse from(User user) {
            return new UserResponse(user.getId(), user.getEmail(), user.getDisplayName());
        }
    }

    /** Access Token은 본문으로만 준다. Refresh Token은 본문에 넣지 않고 HttpOnly Cookie로만 내려보낸다. */
    public record TokenResponse(String accessToken, long expiresIn, UserResponse user) {
    }

    /** 서비스가 Controller에 넘기는 발급 결과. refreshToken 원문은 Cookie 설정에만 쓰인다. */
    record IssuedTokens(TokenResponse body, String refreshToken) {
    }
}
