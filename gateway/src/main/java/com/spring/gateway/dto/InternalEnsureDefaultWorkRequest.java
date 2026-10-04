package com.spring.gateway.dto;

import jakarta.validation.constraints.NotNull;

/**
 * 内部接口：确保默认 work 请求。
 *
 * @author hanbing
 * @since 2026-10-04
 * @param userId 用户 ID
 */
public record InternalEnsureDefaultWorkRequest(
        @NotNull(message = "userId 不能为空")
        Long userId
) {
}
