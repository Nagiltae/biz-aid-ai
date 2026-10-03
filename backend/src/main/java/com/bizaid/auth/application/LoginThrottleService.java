package com.bizaid.auth.application;

import com.bizaid.auth.domain.LoginThrottle;
import com.bizaid.auth.infrastructure.LoginThrottleProperties;
import com.bizaid.auth.infrastructure.LoginThrottleRepository;
import com.bizaid.common.error.ApiException;
import com.bizaid.common.error.ErrorCode;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Clock;
import java.time.Instant;
import java.util.HexFormat;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

/**
 * 로그인 시도 제한. 계정(정규화 이메일)과 접속 IP를 따로 센다.
 *
 * <p>WHY 별도 트랜잭션(REQUIRES_NEW): 로그인 실패는 예외로 본 트랜잭션이 되돌려지지만 실패 횟수는 남아야 한다.
 * <p>BOUNDARY: 성공하면 계정 횟수만 0으로 되돌린다. IP 횟수는 성공으로 지우지 않는다(맞는 계정 하나로 다른 계정 대입을 숨기지 못하게).
 * <p>RISK: 같은 공유기·사무실 IP를 쓰는 사용자들이 IP 잠금을 함께 받을 수 있다. 기준 횟수·시간은 설정으로 바꾼다.
 */
@Service
public class LoginThrottleService {

    private static final String ACCOUNT = "ACCOUNT";
    private static final String IP = "IP";

    private final LoginThrottleRepository throttles;
    private final LoginThrottleProperties properties;
    private final Clock clock;
    private final TransactionTemplate newTransaction;

    public LoginThrottleService(LoginThrottleRepository throttles, LoginThrottleProperties properties, Clock clock,
                                PlatformTransactionManager transactionManager) {
        this.throttles = throttles;
        this.properties = properties;
        this.clock = clock;
        this.newTransaction = new TransactionTemplate(transactionManager);
        this.newTransaction.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRES_NEW);
    }

    /** 계정이나 IP가 잠겨 있으면 비밀번호를 확인하기 전에 막는다. */
    public void checkAllowed(String email, String ip) {
        Instant now = clock.instant();
        boolean locked = Boolean.TRUE.equals(newTransaction.execute(status ->
                isLocked(key(ACCOUNT, email), now) || (ip != null && isLocked(key(IP, ip), now))));
        if (locked) {
            throw new ApiException(ErrorCode.AUTH_LOGIN_LOCKED);
        }
    }

    /** 실패 1회 기록. 이번 실패로 잠겼는지 돌려준다(활동 기록용). */
    public boolean recordFailure(String email, String ip) {
        boolean locked = record(ACCOUNT, email);
        if (ip != null) {
            locked |= record(IP, ip);
        }
        return locked;
    }

    public void recordSuccess(String email) {
        newTransaction.executeWithoutResult(status -> throttles.findById(key(ACCOUNT, email)).ifPresent(throttles::delete));
    }

    private boolean isLocked(String throttleKey, Instant now) {
        return throttles.findById(throttleKey).map(throttle -> throttle.isLocked(now)).orElse(false);
    }

    private boolean record(String type, String value) {
        String throttleKey = key(type, value);
        try {
            return Boolean.TRUE.equals(newTransaction.execute(status -> recordInTransaction(throttleKey, type)));
        } catch (DataIntegrityViolationException exception) {
            // EXCEPTION: 같은 key의 첫 실패가 동시에 들어와 INSERT가 겹친 경우. 이미 생긴 행에 한 번 더 기록한다.
            return Boolean.TRUE.equals(newTransaction.execute(status -> recordInTransaction(throttleKey, type)));
        }
    }

    private boolean recordInTransaction(String throttleKey, String type) {
        Instant now = clock.instant();
        LoginThrottle throttle = throttles.findById(throttleKey).orElseGet(() -> new LoginThrottle(throttleKey, type, now));
        throttle.recordFailure(now, properties.maxFailures(), properties.lockDuration());
        throttles.saveAndFlush(throttle);
        return throttle.isLocked(now);
    }

    // BOUNDARY: 이메일·IP 원문을 DB에 남기지 않도록 종류를 붙여 SHA-256으로 바꾼다(이메일은 호출 전에 정규화된 값).
    static String key(String type, String value) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest((type + ":" + value).getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException(exception);
        }
    }
}
