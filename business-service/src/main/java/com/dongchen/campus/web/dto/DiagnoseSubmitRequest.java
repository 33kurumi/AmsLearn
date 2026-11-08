package com.dongchen.campus.web.dto;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;

import java.util.List;

public record DiagnoseSubmitRequest(@NotNull(message = "answers 不能为空") @Valid List<Answer> answers) {

    public record Answer(String questionId, String answer) {
    }
}
