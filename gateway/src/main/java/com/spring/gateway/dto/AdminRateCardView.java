package com.spring.gateway.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

import java.math.BigDecimal;

/**
 * 管理后台的模型资费卡行。
 *
 * @author hanbing
 * @since 2026-10-05
 * @param id               资费卡 ID（字符串：雪花 ID 超 2^53，JS 数字会丢精度）
 * @param modelName        模型名
 * @param inputPoints      无缓存输入费率（积分/百万 tokens）
 * @param cacheReadPoints  缓存命中输入费率
 * @param cacheWritePoints 缓存写入费率
 * @param outputPoints     输出费率
 * @param enabled          是否启用
 * @param createdAt        创建时间（ISO UTC）
 * @param updatedAt        更新时间（ISO UTC）
 */
public record AdminRateCardView(
        String id,
        @JsonProperty("model_name") String modelName,
        @JsonProperty("input_points") BigDecimal inputPoints,
        @JsonProperty("cache_read_points") BigDecimal cacheReadPoints,
        @JsonProperty("cache_write_points") BigDecimal cacheWritePoints,
        @JsonProperty("output_points") BigDecimal outputPoints,
        Boolean enabled,
        @JsonProperty("created_at") String createdAt,
        @JsonProperty("updated_at") String updatedAt
) {
}
