package com.dongchen.campus.common;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * 便捷构造保持插入顺序的 Map（允许 null 值）。
 */
public final class Maps {

    private Maps() {
    }

    public static Map<String, Object> of(Object... keyValues) {
        if (keyValues.length % 2 != 0) {
            throw new IllegalArgumentException("keyValues 必须成对出现");
        }
        Map<String, Object> map = new LinkedHashMap<>();
        for (int i = 0; i < keyValues.length; i += 2) {
            map.put(String.valueOf(keyValues[i]), keyValues[i + 1]);
        }
        return map;
    }
}
