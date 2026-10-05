package com.spring.gateway.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

import java.math.BigDecimal;

/**
 * 积分预扣行（管理后台对账视图）。
 *
 * @author hanbing
 * @since 2026-10-05
 * @param turnId    轮次 ID（预扣单号）
 * @param userId    所属用户 ID（字符串）
 * @param amount    预扣额
 * @param status    状态（HELD/SETTLED/RELEASED）
 * @param createdAt 创建时间（ISO UTC）
 * @param settledAt 收口时间（ISO UTC，在途为 null）
 */
public record PointsHoldView(
        @JsonProperty("turn_id") String turnId,
        @JsonProperty("user_id") String userId,
        BigDecimal amount,
        String status,
        @JsonProperty("created_at") String createdAt,
        @JsonProperty("settled_at") String settledAt
) {
}
