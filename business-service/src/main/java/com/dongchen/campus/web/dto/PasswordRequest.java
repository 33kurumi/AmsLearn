package com.dongchen.campus.web.dto;

import jakarta.validation.constraints.NotBlank;

public record PasswordRequest(@NotBlank(message = "原密码不能为空") String oldPassword,
                              @NotBlank(message = "新密码不能为空") String newPassword) {
}
