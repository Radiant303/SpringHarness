package com.spring.gateway.dto;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

/**
 * 绑定邮箱请求。code 在 send-bind-code 阶段可不传。
 *
 * @author hanbing
 * @since 2026-10-10
 * @param email 待绑定邮箱
 * @param code  6 位邮箱验证码（绑定场景；发码请求时为空）
 */
public record BindEmailRequest(
        @NotBlank(message = "邮箱不能为空")
        @Email(message = "邮箱格式不正确")
        @Size(max = 128, message = "邮箱长度不能超过 128")
        String email,

        @Pattern(regexp = "\\d{6}", message = "验证码为 6 位数字")
        String code
) {
}
