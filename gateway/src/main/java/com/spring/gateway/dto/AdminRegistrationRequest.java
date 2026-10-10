package com.spring.gateway.dto;

import jakarta.validation.constraints.NotNull;

/**
 * 注册开关请求。
 *
 * @author hanbing
 * @since 2026-10-05
 * @param open 是否开放注册
 */
public record AdminRegistrationRequest(
        @NotNull Boolean open
) {
}
