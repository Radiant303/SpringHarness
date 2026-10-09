package com.spring.gateway.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

/**
 * Provider 的新建/修改请求。
 *
 * @author hanbing
 * @since 2026-10-09
 * @param name    Provider 名（模型定义经它引用）
 * @param type    类型：openai / alibaba / deepseek / responses
 * @param apiKey  API Key；留空 = 保持不变（新建时必填由服务端判空）
 * @param baseUrl 自定义 base_url；留空 = 保持不变
 */
public record AdminProviderRequest(
        @NotBlank(message = "Provider 名不能为空")
        @Size(max = 64, message = "Provider 名长度不能超过 64")
        @Pattern(regexp = "^[a-z0-9][a-z0-9-]*$", message = "Provider 名只能含小写字母、数字、连字符")
        String name,

        @NotBlank(message = "类型不能为空")
        String type,

        @Size(max = 256, message = "API Key 长度不能超过 256")
        String apiKey,

        @Size(max = 256, message = "base_url 长度不能超过 256")
        String baseUrl
) {
}
