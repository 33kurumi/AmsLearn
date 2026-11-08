package com.dongchen.campus.web.dto;

import jakarta.validation.constraints.NotBlank;

/**
 * 答疑请求：conversationId 可为数字或字符串，为空时由服务端新建会话。
 */
public record ChatRequest(@NotBlank(message = "提问内容不能为空") String message,
                          String imageUrl,
                          Object conversationId) {
}
