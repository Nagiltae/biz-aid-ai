package com.bizaid.activity.application;

import com.bizaid.activity.domain.ActivityAction;
import com.bizaid.activity.domain.ActivityLog;
import com.bizaid.activity.infrastructure.ActivityLogRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Clock;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

/**
 * 사용자 활동 기록 경계. 각 Application Service가 흐름의 결과를 알게 된 지점에서 명시적으로 호출한다.
 *
 * <p>WHY 명시 호출(AOP 대신): 무엇을 언제 어떤 metadata로 남기는지가 서비스 코드에 그대로 보인다. 로그인 실패 이유,
 * AI 결과 종류처럼 흐름 안에서만 아는 값을 넣기도 쉽다.
 * <p>WHY 별도 트랜잭션(REQUIRES_NEW): 로그인 실패처럼 본 트랜잭션이 되돌려지는 경우에도 기록이 남아야 한다.
 * <p>RISK: 기록 실패가 사용자 요청을 실패시키면 안 되므로 예외는 서버 로그로만 남긴다.
 * metadata에는 식별자·결과 종류·개수 같은 값만 넣는다(비밀번호·토큰·키·질문/답변 전문 금지).
 */
@Service
public class ActivityLogService {

    private static final Logger log = LoggerFactory.getLogger(ActivityLogService.class);

    private final ActivityLogRepository logs;
    private final ObjectMapper objectMapper;
    private final Clock clock;
    private final TransactionTemplate newTransaction;

    public ActivityLogService(ActivityLogRepository logs, ObjectMapper objectMapper, Clock clock,
                              PlatformTransactionManager transactionManager) {
        this.logs = logs;
        this.objectMapper = objectMapper;
        this.clock = clock;
        this.newTransaction = new TransactionTemplate(transactionManager);
        this.newTransaction.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRES_NEW);
    }

    public void success(ActivityAction action, Long userId, String targetType, Object targetId, Map<String, ?> metadata) {
        record(action, userId, targetType, targetId, true, null, metadata);
    }

    public void failure(ActivityAction action, Long userId, String targetType, Object targetId, String errorCode,
                        Map<String, ?> metadata) {
        record(action, userId, targetType, targetId, false, errorCode, metadata);
    }

    private void record(ActivityAction action, Long userId, String targetType, Object targetId, boolean success,
                          String errorCode, Map<String, ?> metadata) {
        try {
            String json = metadata == null || metadata.isEmpty() ? null : objectMapper.writeValueAsString(metadata);
            ActivityLog entry = new ActivityLog(userId, action, targetType, targetId == null ? null : String.valueOf(targetId),
                    success, errorCode, json, clock.instant());
            newTransaction.executeWithoutResult(status -> logs.save(entry));
        } catch (Exception exception) {
            log.warn("activity log write failed action={} type={}", action, exception.getClass().getSimpleName());
        }
    }
}
