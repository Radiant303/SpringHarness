package com.spring.gateway.dto;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

import java.util.List;

/**
 * 模型定义的新建/修改请求。capabilities/supportEfforts 以数组传入，服务端存 CSV。
 *
 * @author hanbing
 * @since 2026-10-09
 * @param id             模型 ID（"provider/模型名"，新建后不可改）
 * @param provider       所属 Provider（必须已存在）
 * @param model          实际模型名（API 请求的 model 字段）
 * @param displayName    展示名
 * @param maxContextSize 上下文窗口（tokens）
 * @param maxOutputSize  输出上限（tokens），0 = 不限
 * @param capabilities   能力列表（thinking/always_thinking/image_in/tool_use）
 * @param supportEfforts 支持的思考档位
 * @param defaultEffort  默认思考档位；空 = 不指定
 * @param reasoningKey   推理内容字段名；空 = 无
 * @param enabled        是否启用
 */
public record AdminModelDefRequest(
        @NotBlank(message = "模型 ID 不能为空")
        @Size(max = 128, message = "模型 ID 长度不能超过 128")
        @Pattern(regexp = "^[a-z0-9][a-z0-9-]*/\\S+$", message = "模型 ID 形如 provider/模型名")
        String id,

        @NotBlank(message = "Provider 不能为空")
        String provider,

        @NotBlank(message = "模型名不能为空")
        @Size(max = 128, message = "模型名长度不能超过 128")
        String model,

        @NotBlank(message = "展示名不能为空")
        @Size(max = 64, message = "展示名长度不能超过 64")
        String displayName,

        @NotNull(message = "上下文窗口不能为空")
        @Min(value = 1, message = "上下文窗口必须为正数")
        Long maxContextSize,

        @NotNull(message = "输出上限不能为空")
        @Min(value = 0, message = "输出上限不能为负")
        Long maxOutputSize,

        List<String> capabilities,
        List<String> supportEfforts,

        @Size(max = 16, message = "默认档位长度不能超过 16")
        String defaultEffort,

        @Size(max = 64, message = "推理字段名长度不能超过 64")
        String reasoningKey,

        @NotNull(message = "enabled 不能为空")
        Boolean enabled
) {
}
