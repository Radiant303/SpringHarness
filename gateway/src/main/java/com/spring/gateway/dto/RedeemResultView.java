package com.spring.gateway.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

import java.math.BigDecimal;

/**
 * 兑换结果：实发三项面值 + 入账后积分余额。
 *
 * @author hanbing
 * @since 2026-10-06
 * @param grantedPoints         实发积分
 * @param grantedStorageBytes   实发存储配额增量（字节）
 * @param grantedWorkQuotaBytes 实发单工作区上限增量（字节）
 * @param balanceAfter          入账后积分余额
 */
public record RedeemResultView(
        @JsonProperty("granted_points") BigDecimal grantedPoints,
        @JsonProperty("granted_storage_bytes") Long grantedStorageBytes,
        @JsonProperty("granted_work_quota_bytes") Long grantedWorkQuotaBytes,
        @JsonProperty("balance_after") BigDecimal balanceAfter
) {
}
