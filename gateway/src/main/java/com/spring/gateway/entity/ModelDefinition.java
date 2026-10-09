package com.spring.gateway.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

/**
 * model_definitions 表的实体：可供用户选择的模型定义（站长在管理后台维护）。
 *
 * <p>id 形如 "provider/模型名"，是全局唯一标识：前端模型 picker、usage_records.model_name
 * 计费匹配都用它。
 *
 * @author hanbing
 * @since 2026-10-09
 */
@Data
@TableName("model_definitions")
public class ModelDefinition {

    /** 模型 ID（"provider/模型名"），主键。 */
    @TableId(type = IdType.INPUT)
    private String id;

    /** 所属 Provider（model_providers.name）。 */
    private String provider;

    /** 实际模型名（API 请求里的 model 字段）。 */
    private String model;

    /** 展示名（前端 picker 显示）。 */
    private String displayName;

    /** 上下文窗口大小（tokens）。 */
    private Long maxContextSize;

    /** 单次输出上限（tokens）；0 = 不限制。 */
    private Long maxOutputSize;

    /** 能力列表，CSV（thinking,always_thinking,image_in,tool_use）。 */
    private String capabilities;

    /** 支持的思考档位，CSV（low,medium,high）。 */
    private String supportEfforts;

    /** 默认思考档位；空串 = 不指定。 */
    private String defaultEffort;

    /** 推理内容在响应里的字段名（如 reasoning_content）；空 = 无。 */
    private String reasoningKey;

    /** 是否启用；停用后不出现在用户 picker。 */
    private Boolean enabled;

    /** 创建时间（UTC）。 */
    private LocalDateTime createdAt;

    /** 更新时间（UTC）。 */
    private LocalDateTime updatedAt;
}
