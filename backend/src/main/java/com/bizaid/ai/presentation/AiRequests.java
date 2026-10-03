package com.bizaid.ai.presentation;

import com.bizaid.ai.application.AiDtos;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.PositiveOrZero;
import jakarta.validation.constraints.Size;
import java.util.Map;

/** AI HTTP 요청 DTO. 입력 검증은 HTTP 경계에서 하고 Application Service에는 검증된 값만 넘긴다. */
public final class AiRequests {

    private AiRequests() {
    }

    /** conversationId가 없으면 새 대화를 만들어 질문을 저장한다. */
    public record AiQueryRequest(
            @NotBlank(message = "질문을 입력해 주세요.") @Size(max = 2000, message = "질문은 2000자 이하로 입력해 주세요.")
            String query,
            Long conversationId,
            @Pattern(regexp = "^PBLN_[0-9]{12,20}$", message = "공고 ID 형식이 올바르지 않습니다.") String selectedPblancId) {
    }

    /** V2 개인화 검색 질문. 기업정보는 요청으로 받지 않고 로그인 사용자의 저장된 기업정보를 쓴다. */
    public record PersonalizedSearchRequest(
            @NotBlank(message = "질문을 입력해 주세요.") @Size(max = 2000, message = "질문은 2000자 이하로 입력해 주세요.")
            String query) {
    }

    /** 자격 판정 때만 받는 일시 정보(저장하지 않음). */
    public record EligibilityRequest(
            @PositiveOrZero(message = "신용점수는 0 이상이어야 합니다.") @Max(value = 1000, message = "신용점수는 1000 이하입니다.")
            Integer creditScore,
            Boolean taxDelinquent,
            @Size(max = 20, message = "추가 정보는 20개까지 입력할 수 있습니다.") Map<String, Object> additionalFacts) {

        AiDtos.TemporaryFacts toFacts() {
            return new AiDtos.TemporaryFacts(creditScore, taxDelinquent, additionalFacts);
        }
    }
}
