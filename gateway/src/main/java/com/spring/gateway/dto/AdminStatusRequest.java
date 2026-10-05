package com.spring.gateway.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;

/**
 * 禁用/启用账号请求。
 *
 * @author hanbing
 * @since 2026-10-05
 * @param status 目标状态（active/disabled）
 */
public record AdminStatusRequest(
        @NotBlank @Pattern(regexp = "active|disabled", message = "status 只能是 active 或 disabled")
        String status
) {
}
