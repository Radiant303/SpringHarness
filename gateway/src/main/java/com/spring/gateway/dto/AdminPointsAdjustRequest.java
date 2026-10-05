package com.spring.gateway.dto;

import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import java.math.BigDecimal;

/**
 * 站长调账请求（充值/扣减积分）。
 *
 * @author hanbing
 * @since 2026-10-05
 * @param delta  变动额（正=充值，负=扣减，不能为 0；余额不许调成负）
 * @param reason 事由（记账备查）
 */
public record AdminPointsAdjustRequest(
        @NotNull BigDecimal delta,
        @NotNull @Size(min = 1, max = 255) String reason
) {
}
