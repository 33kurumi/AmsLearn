package com.dongchen.campus.web.dto;

import jakarta.validation.constraints.NotNull;

public record WrongQuestionRequest(@NotNull(message = "reviewed 不能为空") Boolean reviewed) {
}
