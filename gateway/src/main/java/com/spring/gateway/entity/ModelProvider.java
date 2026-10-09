package com.spring.gateway.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

/**
 * model_providers 表的实体：模型 Provider（站长在管理后台维护）。
 *
 * <p>api_key 敏感：接口只写不读，GET 只回"是否已配置"。
 *
 * @author hanbing
 * @since 2026-10-09
 */
@Data
@TableName("model_providers")
public class ModelProvider {

    /** 支持的 Provider 类型（决定引擎侧用哪个 pydantic-ai Provider 构建模型）。 */
    public static final java.util.Set<String> SUPPORTED_TYPES =
            java.util.Set.of("openai", "alibaba", "deepseek", "responses");

    /** Provider 名，主键（模型定义经 provider 列引用）。 */
    @TableId(type = IdType.INPUT)
    private String name;

    /** 类型：openai / alibaba / deepseek / responses。 */
    private String type;

    /** API Key。 */
    private String apiKey;

    /** 自定义 base_url（deepseek 类型用官方地址，可为空）。 */
    private String baseUrl;

    /** 更新时间（UTC）。 */
    private LocalDateTime updatedAt;
}
