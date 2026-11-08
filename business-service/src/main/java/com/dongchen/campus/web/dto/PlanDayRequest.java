package com.dongchen.campus.web.dto;

import jakarta.validation.constraints.NotNull;

public record PlanDayRequest(@NotNull(message = "done 不能为空") Boolean done) {
}
