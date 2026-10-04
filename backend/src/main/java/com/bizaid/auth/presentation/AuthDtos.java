package com.bizaid.auth.presentation;

import com.bizaid.auth.domain.User;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

/** 인증 HTTP 요청·응답 DTO. 엔티티를 응답으로 직접 내보내지 않도록 필요한 값만 담는다. */
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
            String displayName,
            // 필수 동의(묶음5-1). 값이 없거나 false면 가입하지 않는다(validation_failed + 항목별 안내).
            // EXCEPTION: @AssertTrue는 null을 통과시키므로 @NotNull을 함께 둔다.
            @NotNull(message = "이용약관에 동의해 주세요.") @AssertTrue(message = "이용약관에 동의해 주세요.") Boolean agreeTerms,
            @NotNull(message = "개인정보처리방침에 동의해 주세요.") @AssertTrue(message = "개인정보처리방침에 동의해 주세요.")
            Boolean agreePrivacy) {
    }

    /** 체험하기 화면 상태. 체험 기능을 끈 환경에서는 버튼을 숨긴다. */
    public record TrialStatus(boolean enabled) {
    }

    public record LoginRequest(
            @NotBlank(message = "이메일을 입력해 주세요.") String email,
            @NotBlank(message = "비밀번호를 입력해 주세요.") String password) {
    }

    /** trial=true면 체험 계정이다. 화면은 "체험 중" 표시와 회원가입 버튼을 보여 주고 수정 기능을 잠근다. */
    public record UserResponse(Long id, String email, String displayName, boolean trial) {

        public static UserResponse from(User user) {
            return new UserResponse(user.getId(), user.getEmail(), user.getDisplayName(), user.isTrial());
        }
    }

    /** Access Token은 본문으로만 준다. Refresh Token은 본문에 넣지 않고 HttpOnly Cookie로만 내려보낸다. */
    public record TokenResponse(String accessToken, long expiresIn, UserResponse user) {
    }


    /** 회원 탈퇴 요청. 현재 비밀번호를 다시 받는다. */
    public record WithdrawRequest(@NotBlank(message = "비밀번호를 입력해 주세요.") String password) {
    }

    /** 비밀번호 변경 요청. 새 비밀번호 규칙은 가입과 같다(8~64자). */
    public record PasswordChangeRequest(
            @NotBlank(message = "현재 비밀번호를 입력해 주세요.") String currentPassword,
            @NotBlank(message = "새 비밀번호를 입력해 주세요.") @Size(min = 8, max = 64, message = "비밀번호는 8~64자로 입력해 주세요.")
            String newPassword) {
    }
}
