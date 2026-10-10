package com.spring.gateway.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

/**
 * 邮箱验证码重置密码请求。
 *
 * @author hanbing
 * @since 2026-10-10
 * @param email       注册时验证过的邮箱
 * @param code        6 位邮箱验证码（重置场景）
 * @param newPassword 新密码，至少 6 位
 */
public record ResetPasswordRequest(
        @NotBlank(message = "邮箱不能为空")
        @Size(max = 128, message = "邮箱长度不能超过 128")
        String email,

        @NotBlank(message = "验证码不能为空")
        @Pattern(regexp = "\\d{6}", message = "验证码为 6 位数字")
        String code,

        @NotBlank(message = "新密码不能为空")
        @Size(min = 6, message = "密码至少 6 位")
        String newPassword
) {
}
