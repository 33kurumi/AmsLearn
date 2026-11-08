package com.dongchen.campus.web.dto;

import jakarta.validation.constraints.NotBlank;

public record ConfigExtractRequest(@NotBlank(message = "配置描述不能为空") String text) {
}
