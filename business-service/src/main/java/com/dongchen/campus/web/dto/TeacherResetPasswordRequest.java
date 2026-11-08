package com.dongchen.campus.web.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

/**
 * 教师重置学生密码请求（v1.4）。
 */
public record TeacherResetPasswordRequest(
        @NotBlank(message = "新密码不能为空")
        @Size(min = 6, max = 32, message = "新密码长度应为 6~32 位")
        String newPassword) {
}
