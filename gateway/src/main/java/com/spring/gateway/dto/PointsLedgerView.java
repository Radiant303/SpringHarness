package com.spring.gateway.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

import java.math.BigDecimal;

/**
 * 积分流水行（管理后台与用户自查共用）。
 *
 * @author hanbing
 * @since 2026-10-05
 * @param id           流水 ID（字符串：雪花精度）
 * @param userId       所属用户 ID（字符串）
 * @param changeAmount 变动额（有符号）
 * @param balanceAfter 变动后余额
 * @param type         类型（HOLD/SETTLE/RELEASE/DIRECT/ADJUST）
 * @param refId        关联单号（turn_id 或调账单号）
 * @param modelName    结算时实际模型
 * @param operatorId   ADJUST 操作人 ID（字符串）
 * @param reason       ADJUST 事由
 * @param createdAt    记录时间（ISO UTC）
 */
public record PointsLedgerView(
        String id,
        @JsonProperty("user_id") String userId,
        @JsonProperty("change_amount") BigDecimal changeAmount,
        @JsonProperty("balance_after") BigDecimal balanceAfter,
        String type,
        @JsonProperty("ref_id") String refId,
        @JsonProperty("model_name") String modelName,
        @JsonProperty("operator_id") String operatorId,
        String reason,
        @JsonProperty("created_at") String createdAt
) {
}
