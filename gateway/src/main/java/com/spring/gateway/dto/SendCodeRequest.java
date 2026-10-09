package com.spring.gateway.dto;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

/**
 * 发送注册邮箱验证码请求。
 *
 * @author hanbing
 * @since 2026-10-09
 * @param email 接收验证码的邮箱（QQ 邮箱）
 */
public record SendCodeRequest(
        @NotBlank(message = "邮箱不能为空")
        @Email(message = "邮箱格式不正确")
        @Size(max = 128, message = "邮箱长度不能超过 128")
        String email
) {
}
