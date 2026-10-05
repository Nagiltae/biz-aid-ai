package com.bizaid.auth.application;

import com.bizaid.common.error.ApiException;
import com.bizaid.common.error.ErrorCode;
import com.bizaid.usage.application.AiUsageService;
import com.bizaid.usage.infrastructure.UsageCounterStore;
import com.bizaid.usage.infrastructure.UsageProperties;
import java.time.Clock;
import org.springframework.stereotype.Service;

/** 가입 요청 IP별 하루 제한. 원문 IP는 보관하지 않고 기존 SHA-256 함수를 사용한다. */
@Service
public class SignupThrottleService {
    private final UsageCounterStore store;
    private final UsageProperties properties;
    private final AiUsageService usage;
    private final Clock clock;

    public SignupThrottleService(UsageCounterStore store, UsageProperties properties, AiUsageService usage, Clock clock) {
        this.store = store;
        this.properties = properties;
        this.usage = usage;
        this.clock = clock;
    }

    public void reserve(String clientIp) {
        // BOUNDARY: 실패한 가입도 센다. 개인정보를 저장하지 않고 가입 요청 남용을 제한한다.
        var now = clock.instant();
        if (!store.incrementBelow("SIGNUP_IP:" + AuthService.hash(clientIp), usage.serviceDate(now), properties.signupPerIpPerDay(), now)) {
            throw new ApiException(ErrorCode.AUTH_SIGNUP_LIMITED);
        }
    }
}
