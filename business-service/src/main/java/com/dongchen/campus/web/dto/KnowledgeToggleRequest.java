package com.dongchen.campus.web.dto;

import jakarta.validation.constraints.NotNull;

public record KnowledgeToggleRequest(@NotNull(message = "enabled 不能为空") Boolean enabled) {
}
