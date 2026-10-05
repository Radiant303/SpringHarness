package com.spring.gateway.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

import java.math.BigDecimal;

/**
 * 登录成功返回体
 *
 * @author hanbing
 * @since 2026-09-26
 * @param token         JWT
 * @param userId        用户 ID（字符串：雪花 ID 超 2^53，JS 数字会丢精度）
 * @param username      用户名
 * @param role          角色：owner / admin / user
 * @param pointsBalance 积分余额（登录时刻快照，后续变动经 /api/billing/me 刷新）
 */
public record TokenResponse(
        String token,
        @JsonProperty("user_id") String userId,
        String username,
        String role,
        @JsonProperty("points_balance") BigDecimal pointsBalance
) {
}
