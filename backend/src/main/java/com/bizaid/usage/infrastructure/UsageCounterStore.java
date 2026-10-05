package com.bizaid.usage.infrastructure;

import java.sql.Date;
import java.sql.Timestamp;
import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

/**
 * 사용 횟수의 원자적 증감.
 * WHY: "읽고 비교한 뒤 저장"은 동시 요청 두 개가 같은 값을 읽어 상한을 넘길 수 있다.
 * 상한 비교를 UPDATE의 WHERE에 넣어 DB가 행 잠금으로 한 번에 처리하게 한다(영향 행 1 = 허용, 0 = 상한 도달).
 */
@Repository
public class UsageCounterStore {

    private final JdbcTemplate jdbc;

    public UsageCounterStore(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    /** 상한보다 적을 때만 1 늘린다. 늘렸으면 true. */
    public boolean incrementBelow(String key, LocalDate date, int limit, Instant now) {
        ensureRow(key, date, now);
        return jdbc.update("update ai_usage_counters set used_count = used_count + 1, updated_at = ? "
                + "where counter_key = ? and usage_date = ? and used_count < ?", Timestamp.from(now), key, Date.valueOf(date), limit) == 1;
    }

    /** AI가 결과를 주지 못한 요청의 횟수를 되돌린다. 0 아래로는 내려가지 않는다. */
    public void decrement(String key, LocalDate date, Instant now) {
        jdbc.update("update ai_usage_counters set used_count = used_count - 1, updated_at = ? "
                + "where counter_key = ? and usage_date = ? and used_count > 0", Timestamp.from(now), key, Date.valueOf(date));
    }

    public int used(String key, LocalDate date) {
        List<Integer> rows = jdbc.queryForList("select used_count from ai_usage_counters where counter_key = ? and usage_date = ?",
                Integer.class, key, Date.valueOf(date));
        return rows.isEmpty() ? 0 : rows.get(0);
    }

    public int deleteKey(String key) {
        return jdbc.update("delete from ai_usage_counters where counter_key = ?", key);
    }

    public int deleteBefore(LocalDate date) {
        // BOUNDARY: 한국 날짜 기준 7일 된 행도 지워 IP 해시가 8일째까지 남지 않게 한다.
        return jdbc.update("delete from ai_usage_counters where usage_date <= ?", Date.valueOf(date));
    }

    // WHY INSERT IGNORE: 동시 요청이 같은 날 첫 행을 함께 만들어도 하나만 남고 나머지는 오류 없이 넘어간다.
    // BOUNDARY: 호출하는 쪽에 트랜잭션을 두지 않는다(문장마다 바로 commit). 행 생성 잠금을 오래 잡지 않아 교착을 피한다.
    private void ensureRow(String key, LocalDate date, Instant now) {
        jdbc.update("insert ignore into ai_usage_counters (counter_key, usage_date, used_count, updated_at) values (?, ?, 0, ?)",
                key, Date.valueOf(date), Timestamp.from(now));
    }
}
