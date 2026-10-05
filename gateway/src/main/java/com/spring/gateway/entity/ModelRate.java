package com.spring.gateway.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.math.BigDecimal;
import java.time.LocalDateTime;

/**
 * models 表的实体：模型资费卡。
 *
 * <p>每项费率单位 = 积分/百万 tokens。model_name 与 usage_records.model_name
 * 精确匹配；model_name = "default" 的行是兜底卡：派发预扣估算用它，
 * 结算时实际模型匹配不到（或未启用）也回落到它。
 *
 * @author hanbing
 * @since 2026-10-05
 */
@Data
@TableName("models")
public class ModelRate {

    /** 兜底资费卡的 model_name。 */
    public static final String DEFAULT_MODEL_NAME = "default";

    /** 主键，雪花 ID。 */
    @TableId(type = IdType.INPUT)
    private Long id;

    /** 模型名（与 usage_records.model_name 精确匹配），唯一。 */
    private String modelName;

    /** 无缓存输入费率（积分/百万 tokens）。 */
    private BigDecimal inputPoints;

    /** 缓存命中输入费率（积分/百万 tokens）。 */
    private BigDecimal cacheReadPoints;

    /** 缓存写入费率（积分/百万 tokens）。 */
    private BigDecimal cacheWritePoints;

    /** 输出费率（积分/百万 tokens）。 */
    private BigDecimal outputPoints;

    /** 是否启用；停用后结算按兜底卡计。 */
    private Boolean enabled;

    /** 创建时间（UTC）。 */
    private LocalDateTime createdAt;

    /** 更新时间（UTC）。 */
    private LocalDateTime updatedAt;
}
