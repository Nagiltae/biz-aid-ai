package com.bizaid.usage.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.IdClass;
import jakarta.persistence.Table;
import java.io.Serializable;
import java.time.Instant;
import java.time.LocalDate;

/**
 * 하루 사용 횟수 한 칸(대상 key × 한국 날짜).
 * 증가·감소는 UsageCounterStore의 조건부 UPDATE로만 한다. 엔티티는 테이블 정의와 읽기용이다.
 */
@Entity
@Table(name = "ai_usage_counters")
@IdClass(UsageCounter.Key.class)
public class UsageCounter {

    @Id
    @Column(name = "counter_key", length = 80)
    private String counterKey;

    @Id
    @Column(name = "usage_date")
    private LocalDate usageDate;

    @Column(name = "used_count", nullable = false)
    private int usedCount;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    protected UsageCounter() {
    }

    public int getUsedCount() {
        return usedCount;
    }

    public record Key(String counterKey, LocalDate usageDate) implements Serializable {

        public Key() {
            this(null, null);
        }
    }
}
