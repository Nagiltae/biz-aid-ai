package com.bizaid.common;

import java.util.List;
import java.util.function.Function;
import org.springframework.data.domain.Page;

/** Spring Data Page의 내부 구조를 API에 그대로 노출하지 않도록 목록 응답에 필요한 값만 담는다. page는 0부터 시작한다. */
public record PageResponse<T>(List<T> items, int page, int size, long totalElements, int totalPages) {

    public static <E, T> PageResponse<T> from(Page<E> page, Function<E, T> mapper) {
        return new PageResponse<>(page.getContent().stream().map(mapper).toList(), page.getNumber(), page.getSize(),
                page.getTotalElements(), page.getTotalPages());
    }
}
