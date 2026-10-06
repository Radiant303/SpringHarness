package com.spring.gateway.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import java.math.BigDecimal;

/**
 * 站长生成兑换码的请求。三项面值至少一项大于 0（服务层校验）。
 *
 * @author hanbing
 * @since 2026-10-06
 * @param count         生成数量（1-100）
 * @param points        每码积分面值；null/0 = 不含积分
 * @param storageMb     每码存储配额增量（MB）；null/0 = 不含
 * @param workQuotaMb   每码单工作区上限增量（MB）；null/0 = 不含
 * @param expiresInHours 有效小时数；null = 永久有效
 */
public record AdminRedeemCreateRequest(
        @NotNull @Min(1) @Max(100) Integer count,
        @DecimalMin(value = "0", message = "面值不能为负") BigDecimal points,
        @JsonProperty("storage_mb") @Min(0) Long storageMb,
        @JsonProperty("work_quota_mb") @Min(0) Long workQuotaMb,
        @JsonProperty("expires_in_hours") @Min(1) Long expiresInHours
) {
}
