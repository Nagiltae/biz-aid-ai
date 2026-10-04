package com.bizaid.auth.application;

import com.bizaid.activity.application.ActivityLogService;
import com.bizaid.activity.domain.ActivityAction;
import com.bizaid.auth.domain.AccountType;
import com.bizaid.auth.domain.User;
import com.bizaid.auth.infrastructure.UserRepository;
import com.bizaid.common.error.ApiException;
import com.bizaid.common.error.ErrorCode;
import com.bizaid.company.domain.Company;
import com.bizaid.company.domain.CompanyDetails;
import com.bizaid.company.infrastructure.CompanyRepository;
import com.bizaid.usage.application.AiUsageService;
import com.bizaid.usage.infrastructure.UsageCounterStore;
import com.bizaid.usage.infrastructure.UsageProperties;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.util.Base64;
import java.util.HexFormat;
import java.util.List;
import java.util.UUID;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;

/**
 * 체험 계정(2026-10-04 묶음5-1 사용자 결정).
 * "체험하기"를 누를 때마다 새 임시 사용자를 만든다. 사용자마다 따로 만들어 다른 체험자의 대화·추천이 섞이지 않는다.
 * 합성 기업정보(경기도·소상공인·영업중 등)를 미리 넣어 바로 AI 검색·맞춤 추천을 쓸 수 있게 한다.
 *
 * <p>BOUNDARY: 체험 계정은 비밀번호를 알 수 없는 무작위 값으로 만들어 이메일 로그인으로는 다시 들어올 수 없다.
 * 기업정보 수정·비밀번호 변경·탈퇴는 막고(trial_account_restricted), 생성 ttl(24시간) 뒤 정리 작업이 데이터와 함께 지운다.
 * <p>RISK: 누를 때마다 계정이 생기므로 접속 IP별 하루 생성 수를 제한한다(IP 원문 대신 SHA-256만 key로 쓴다).
 */
@Service
public class TrialService {

    private static final SecureRandom RANDOM = new SecureRandom();
    public static final String TRIAL_DISPLAY_NAME = "체험 사용자";

    private final UserRepository users;
    private final CompanyRepository companies;
    private final ConsentService consents;
    private final AuthService authService;
    private final UserDataPurger purger;
    private final UsageCounterStore usageCounters;
    private final UsageProperties usage;
    private final PasswordEncoder passwordEncoder;
    private final ActivityLogService activityLog;
    private final AiUsageService aiUsage;
    private final Clock clock;
    private final TransactionTemplate transaction;

    public TrialService(UserRepository users, CompanyRepository companies, ConsentService consents, AuthService authService,
                        UserDataPurger purger, UsageCounterStore usageCounters, UsageProperties usage, PasswordEncoder passwordEncoder,
                        ActivityLogService activityLog, AiUsageService aiUsage, Clock clock, PlatformTransactionManager transactionManager) {
        this.transaction = new TransactionTemplate(transactionManager);
        this.users = users;
        this.companies = companies;
        this.consents = consents;
        this.authService = authService;
        this.purger = purger;
        this.usageCounters = usageCounters;
        this.usage = usage;
        this.passwordEncoder = passwordEncoder;
        this.activityLog = activityLog;
        this.aiUsage = aiUsage;
        this.clock = clock;
    }

    public boolean enabled() {
        return usage.trial().enabled();
    }

    public IssuedTokens start(String clientIp) {
        if (!enabled()) {
            throw new ApiException(ErrorCode.TRIAL_DISABLED);
        }
        Instant now = clock.instant();
        LocalDate day = aiUsage.serviceDate(now);
        // BOUNDARY: 생성 횟수는 트랜잭션 밖에서 바로 commit되는 조건부 증가로 센다(행 잠금을 짧게 잡아 동시 요청 교착을 피함).
        // 아래 저장이 실패해도 한 번 쓴 것으로 남는다(남용 방지 쪽으로 기운다).
        if (!usageCounters.incrementBelow("TRIAL_IP:" + sha256(clientIp), day, usage.trial().maxCreatesPerIpPerDay(), now)) {
            throw new ApiException(ErrorCode.TRIAL_CREATE_LIMITED);
        }
        return transaction.execute(status -> create(now, day));
    }

    private IssuedTokens create(Instant now, LocalDate day) {
        String email = "trial-" + UUID.randomUUID() + "@trial.bizaid.invalid";
        User user = users.save(new User(email, passwordEncoder.encode(randomSecret()), TRIAL_DISPLAY_NAME, AccountType.TRIAL, now));
        companies.save(new Company(user.getId(), trialCompany(day), now));
        // 체험하기 버튼 아래 안내("누르면 이용약관·개인정보처리방침에 동의")에 대한 동의를 가입과 같은 방식으로 남긴다.
        consents.recordRequired(user.getId(), now);
        IssuedTokens tokens = authService.issue(user);
        activityLog.success(ActivityAction.TRIAL_START, user.getId(), "USER", user.getId(), null);
        return tokens;
    }

    /** 생성 ttl이 지난 체험 계정과 그 데이터를 지운다. 정리 작업(MaintenanceJob)이 부른다. */
    @Transactional
    public int purgeExpired(Instant now) {
        List<User> expired = users.findByAccountTypeAndCreatedAtBefore(AccountType.TRIAL, now.minus(usage.trial().ttl()));
        expired.forEach(user -> purger.purge(user.getId()));
        return expired.size();
    }

    /** 합성 기업정보(실제 회사 아님). 업력이 늘 3년이 되도록 개업일은 만드는 날 기준으로 정한다. */
    static CompanyDetails trialCompany(LocalDate today) {
        return new CompanyDetails("체험용 가게", "개인사업자", "소상공인", "경기도", "음식점업", today.minusYears(3), "영업중",
                3, 150_000_000L, false, false, false);
    }

    private static String randomSecret() {
        byte[] bytes = new byte[32];
        RANDOM.nextBytes(bytes);
        return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
    }

    private static String sha256(String value) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(String.valueOf(value).getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException(exception);
        }
    }
}
