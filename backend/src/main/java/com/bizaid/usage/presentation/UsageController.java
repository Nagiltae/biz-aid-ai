package com.bizaid.usage.presentation;

import com.bizaid.auth.domain.AuthUser;
import com.bizaid.usage.application.AiUsageService;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

/** 오늘 남은 AI 사용 횟수. 화면이 AI 검색·맞춤 추천 입력 옆에 보여 준다. */
@RestController
public class UsageController {

    private final AiUsageService usageService;

    public UsageController(AiUsageService usageService) {
        this.usageService = usageService;
    }

    @GetMapping("/api/ai/usage")
    public AiUsageService.Usage usage(@AuthenticationPrincipal AuthUser user) {
        return usageService.usage(user.id());
    }
}
