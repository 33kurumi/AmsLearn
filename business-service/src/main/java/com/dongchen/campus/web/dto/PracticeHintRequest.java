package com.dongchen.campus.web.dto;

import jakarta.validation.constraints.NotBlank;

public record PracticeHintRequest(@NotBlank(message = "batchId 不能为空") String batchId,
                                  @NotBlank(message = "questionId 不能为空") String questionId,
                                  String studentAnswer) {
}
