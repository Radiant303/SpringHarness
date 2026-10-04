package com.spring.gateway.dto;

import jakarta.validation.constraints.NotNull;

/**
 * 内部 API：删除会话请求，带归属校验用的用户 ID。
 *
 * @author hanbing
 * @since 2026-10-03
 * @param userId 发起删除的用户 ID
 */
public record InternalDeleteSessionRequest(
        @NotNull(message = "userId 不能为空")
        Long userId
) {
}
