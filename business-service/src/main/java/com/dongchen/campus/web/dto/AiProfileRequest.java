package com.dongchen.campus.web.dto;

/**
 * 用户 AI 配置更新请求：字段为 null 表示不变；apiKey 传空串表示清除。
 */
public record AiProfileRequest(String apiKey, String baseUrl, String model, Boolean enabled) {
}
