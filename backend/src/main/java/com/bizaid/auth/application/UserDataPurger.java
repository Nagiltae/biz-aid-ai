package com.bizaid.auth.application;

import com.bizaid.activity.infrastructure.ActivityLogRepository;
import com.bizaid.ai.infrastructure.AiWorkflowRepository;
import com.bizaid.auth.infrastructure.RefreshTokenRepository;
import com.bizaid.auth.infrastructure.UserConsentRepository;
import com.bizaid.auth.infrastructure.UserRepository;
import com.bizaid.company.infrastructure.CompanyRepository;
import com.bizaid.conversation.infrastructure.ConversationRepository;
import com.bizaid.conversation.infrastructure.MessageRepository;
import com.bizaid.usage.application.AiUsageService;
import com.bizaid.usage.infrastructure.UsageCounterStore;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

/**
 * 한 사용자의 서비스 데이터를 모두 지운다. 회원 탈퇴와 만료된 체험 계정 정리가 같은 규칙을 쓴다.
 * 지우는 것: 메시지·대화·추천 흐름·기업정보·Refresh Token·동의 기록·하루 사용 횟수·사용자 행.
 * 남기는 것: 활동 기록(user_id·대상 id를 지워 누구인지 알 수 없게).
 */
@Component
public class UserDataPurger {

    private final UserRepository users;
    private final RefreshTokenRepository refreshTokens;
    private final CompanyRepository companies;
    private final ConversationRepository conversations;
    private final MessageRepository messages;
    private final AiWorkflowRepository workflows;
    private final UserConsentRepository consents;
    private final ActivityLogRepository activityLogs;
    private final UsageCounterStore usageCounters;

    public UserDataPurger(UserRepository users, RefreshTokenRepository refreshTokens, CompanyRepository companies,
                          ConversationRepository conversations, MessageRepository messages, AiWorkflowRepository workflows,
                          UserConsentRepository consents, ActivityLogRepository activityLogs, UsageCounterStore usageCounters) {
        this.users = users;
        this.refreshTokens = refreshTokens;
        this.companies = companies;
        this.conversations = conversations;
        this.messages = messages;
        this.workflows = workflows;
        this.consents = consents;
        this.activityLogs = activityLogs;
        this.usageCounters = usageCounters;
    }

    @Transactional(propagation = Propagation.MANDATORY)
    public void purge(Long userId) {
        // BOUNDARY: 외래키 순서대로 자식 행부터 지운다(messages → conversations, 나머지는 users만 참조).
        messages.deleteAllByUser(userId);
        conversations.deleteAllByUser(userId);
        workflows.deleteAllByUser(userId);
        companies.deleteAllByUser(userId);
        refreshTokens.deleteAllByUser(userId);
        consents.deleteAllByUser(userId);
        usageCounters.deleteKey(AiUsageService.userKey(userId));
        activityLogs.anonymizeUser(userId);
        users.deleteById(userId);
    }
}
