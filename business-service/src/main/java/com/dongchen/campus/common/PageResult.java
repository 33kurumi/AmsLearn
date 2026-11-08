package com.dongchen.campus.common;

import java.util.List;

/**
 * 统一分页结构：{ items, page, size, total, hasNext }。
 */
public record PageResult<T>(List<T> items, int page, int size, long total, boolean hasNext) {

    public static final int DEFAULT_SIZE = 10;
    public static final int MAX_SIZE = 100;

    public static <T> PageResult<T> of(List<T> all, Integer page, Integer size) {
        int p = normalizePage(page);
        int s = normalizeSize(size);
        int total = all == null ? 0 : all.size();
        int from = Math.min(Math.max((p - 1) * s, 0), total);
        int to = Math.min(from + s, total);
        return new PageResult<>(all == null ? List.of() : all.subList(from, to), p, s, total, to < total);
    }

    public static int normalizePage(Integer page) {
        return page == null || page < 1 ? 1 : page;
    }

    public static int normalizeSize(Integer size) {
        if (size == null || size < 1) {
            return DEFAULT_SIZE;
        }
        return Math.min(size, MAX_SIZE);
    }
}
