package com.spring.gateway.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

/**
 * 重置密码请求。
 *
 * @author hanbing
 * @since 2026-10-05
 * @param password 新密码
 */
public record AdminPasswordRequest(
        @NotBlank @Size(min = 6, max = 64, message = "密码长度需在 6-64 位之间")
        String password
) {
}
