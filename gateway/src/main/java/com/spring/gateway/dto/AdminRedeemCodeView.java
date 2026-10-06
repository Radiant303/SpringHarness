package com.spring.gateway.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

import java.math.BigDecimal;

/**
 * 管理侧兑换码视图。id 与用户 ID 转字符串防 JS 雪花精度丢失；
 * expired 由视图层按 expires_at 计算（不建 EXPIRED 状态）。
 *
 * @author hanbing
 * @since 2026-10-06
 * @param id                 码 ID（字符串）
 * @param code               兑换码（规范形）
 * @param status             ACTIVE / REDEEMED / REVOKED
 * @param expired            是否已过期（ACTIVE 且 expires_at 已过）
 * @param points             积分面值
 * @param storageDeltaBytes  存储配额增量（字节）
 * @param workQuotaDeltaBytes 单工作区上限增量（字节）
 * @param expiresAt          失效时间（ISO UTC），null 永久
 * @param createdBy          生成人用户 ID（字符串）
 * @param redeemedBy         兑换人用户 ID（字符串），未兑换为 null
 * @param redeemedAt         兑换时间（ISO UTC）
 * @param createdAt          创建时间（ISO UTC）
 */
public record AdminRedeemCodeView(
        String id,
        String code,
        String status,
        boolean expired,
        BigDecimal points,
        @JsonProperty("storage_delta_bytes") Long storageDeltaBytes,
        @JsonProperty("work_quota_delta_bytes") Long workQuotaDeltaBytes,
        @JsonProperty("expires_at") String expiresAt,
        @JsonProperty("created_by") String createdBy,
        @JsonProperty("redeemed_by") String redeemedBy,
        @JsonProperty("redeemed_at") String redeemedAt,
        @JsonProperty("created_at") String createdAt
) {
}
