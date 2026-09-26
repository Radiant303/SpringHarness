package com.spring.gateway.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

/**
 * 注册请求。校验规则与 Python 侧 schemas.RegisterRequest 保持一致。
 *
 * @author hanbing
 * @since 2026-09-26
 * @param username 用户名，长度 2~64
 * @param password 密码，至少 6 位
 */
public record RegisterRequest(
        @NotBlank(message = "用户名不能为空")
        @Size(min = 2, max = 64, message = "用户名长度需 2~64")
        String username,

        @NotBlank(message = "密码不能为空")
        @Size(min = 6, message = "密码至少 6 位")
        String password
) {
}
