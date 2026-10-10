package com.spring.gateway.dto;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import java.math.BigDecimal;

/**
 * 模型资费卡的新建/修改请求；费率单位 = 积分/百万 tokens。
 *
 * @author hanbing
 * @since 2026-10-05
 * @param modelName        模型名（与 usage_records.model_name 精确匹配）
 * @param inputPoints      无缓存输入费率
 * @param cacheReadPoints  缓存命中输入费率
 * @param cacheWritePoints 缓存写入费率
 * @param outputPoints     输出费率
 * @param enabled          是否启用；null 视为启用
 */
public record AdminRateCardRequest(
        @NotBlank @Size(max = 128) String modelName,
        @NotNull @DecimalMin(value = "0", message = "费率不能为负") BigDecimal inputPoints,
        @NotNull @DecimalMin(value = "0", message = "费率不能为负") BigDecimal cacheReadPoints,
        @NotNull @DecimalMin(value = "0", message = "费率不能为负") BigDecimal cacheWritePoints,
        @NotNull @DecimalMin(value = "0", message = "费率不能为负") BigDecimal outputPoints,
        Boolean enabled
) {
}
