package com.dongchen.campus.web.dto;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;

import java.util.List;

/**
 * v1.3 前置自测提交：gateId + 所属会话 + 作答（questionId/choice）。
 */
public record GateCheckRequest(
        @NotBlank(message = "不能为空") String gateId,
        Object conversationId,
        @NotEmpty(message = "请提交前置测试答案") @Valid List<Answer> answers) {

    public record Answer(@NotBlank(message = "questionId 不能为空") String questionId,
                         @NotBlank(message = "choice 不能为空") String choice) {
    }
}
