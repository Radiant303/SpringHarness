package com.spring.gateway.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

import java.math.BigDecimal;

/**
 * 用户自己的一条兑换记录（来自 redeem_codes 的审计行）。
 *
 * @author hanbing
 * @since 2026-10-06
 * @param code               兑换码（规范形）
 * @param grantedPoints      兑换所得积分
 * @param grantedStorageBytes 兑换所得存储配额增量（字节）
 * @param grantedWorkQuotaBytes 兑换所得单工作区上限增量（字节）
 * @param redeemedAt         兑换时间（ISO UTC）
 */
public record MyRedemptionView(
        String code,
        @JsonProperty("granted_points") BigDecimal grantedPoints,
        @JsonProperty("granted_storage_bytes") Long grantedStorageBytes,
        @JsonProperty("granted_work_quota_bytes") Long grantedWorkQuotaBytes,
        @JsonProperty("redeemed_at") String redeemedAt
) {
}
