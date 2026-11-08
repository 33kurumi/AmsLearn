package com.dongchen.campus.web.dto;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

/**
 * 学生注册请求（v1.4）：username 4~20 位字母/数字/下划线，password 6~32 位。
 */
public record RegisterRequest(
        @NotBlank(message = "用户名不能为空")
        @Pattern(regexp = "^[A-Za-z0-9_]{4,20}$", message = "用户名应为 4~20 位字母、数字或下划线")
        String username,
        @NotBlank(message = "密码不能为空")
        @Size(min = 6, max = 32, message = "密码长度应为 6~32 位")
        String password,
        @NotBlank(message = "昵称不能为空")
        String displayName,
        @Email(message = "邮箱格式不正确")
        String email) {
}
