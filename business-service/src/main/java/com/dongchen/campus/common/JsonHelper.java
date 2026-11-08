package com.dongchen.campus.common;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 统一 JSON 文本 <-> Map/List 转换（数据库中以 JSON 文本保存的字段使用）。
 */
@Component
public class JsonHelper {

    private static final Logger log = LoggerFactory.getLogger(JsonHelper.class);

    private final ObjectMapper objectMapper;

    public JsonHelper(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    public ObjectMapper mapper() {
        return objectMapper;
    }

    public String write(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (Exception ex) {
            throw new BusinessException(ErrorCode.INTERNAL_ERROR, "JSON 序列化失败");
        }
    }

    public Map<String, Object> readMap(String json) {
        if (json == null || json.isBlank()) {
            return new LinkedHashMap<>();
        }
        try {
            return objectMapper.readValue(json, new TypeReference<LinkedHashMap<String, Object>>() {
            });
        } catch (Exception ex) {
            log.warn("JSON 文本解析为 Map 失败: {}", abbreviate(json));
            return new LinkedHashMap<>();
        }
    }

    public List<Object> readList(String json) {
        if (json == null || json.isBlank()) {
            return new ArrayList<>();
        }
        try {
            return objectMapper.readValue(json, new TypeReference<List<Object>>() {
            });
        } catch (Exception ex) {
            log.warn("JSON 文本解析为 List 失败: {}", abbreviate(json));
            return new ArrayList<>();
        }
    }

    public List<String> readStringList(String json) {
        List<String> result = new ArrayList<>();
        for (Object item : readList(json)) {
            if (item != null) {
                result.add(String.valueOf(item));
            }
        }
        return result;
    }

    public JsonNode readTree(String json) {
        try {
            return objectMapper.readTree(json == null ? "{}" : json);
        } catch (Exception ex) {
            throw new BusinessException(ErrorCode.INTERNAL_ERROR, "JSON 解析失败");
        }
    }

    public Map<String, Object> toMap(Object value) {
        if (value == null) {
            return new LinkedHashMap<>();
        }
        try {
            return objectMapper.convertValue(value, new TypeReference<LinkedHashMap<String, Object>>() {
            });
        } catch (Exception ex) {
            return new LinkedHashMap<>();
        }
    }

    public List<Object> toList(Object value) {
        if (value == null) {
            return new ArrayList<>();
        }
        try {
            return objectMapper.convertValue(value, new TypeReference<List<Object>>() {
            });
        } catch (Exception ex) {
            return new ArrayList<>();
        }
    }

    public List<Map<String, Object>> toMapList(JsonNode node) {
        List<Map<String, Object>> result = new ArrayList<>();
        if (node == null || !node.isArray()) {
            return result;
        }
        for (JsonNode item : node) {
            result.add(toMap(item));
        }
        return result;
    }

    public List<String> toStringList(JsonNode node) {
        List<String> result = new ArrayList<>();
        if (node == null || !node.isArray()) {
            return result;
        }
        for (JsonNode item : node) {
            result.add(item.asText());
        }
        return result;
    }

    public String nodeText(JsonNode node, String field, String fallback) {
        if (node == null) {
            return fallback;
        }
        JsonNode value = node.get(field);
        return value == null || value.isNull() ? fallback : value.asText(fallback);
    }

    private String abbreviate(String text) {
        if (text == null) {
            return "null";
        }
        return text.length() <= 120 ? text : text.substring(0, 120) + "...";
    }
}
