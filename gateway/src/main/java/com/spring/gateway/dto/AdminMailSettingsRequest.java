package com.spring.gateway.dto;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

/**
 * 站长配置邮箱验证码注册（QQ 邮箱 SMTP）。
 *
 * @author hanbing
 * @since 2026-10-09
 * @param enabled               是否开启邮箱验证码注册
 * @param username              发件 QQ 邮箱；留空 = 保持不变
 * @param authCode              SMTP 授权码；留空 = 保持不变（接口只写不读）
 * @param resendIntervalSeconds 同一邮箱重发间隔（秒）
 * @param codeTtlSeconds        验证码有效期（秒）
 */
public record AdminMailSettingsRequest(
        @NotNull(message = "enabled 不能为空")
        Boolean enabled,

        @Size(max = 128, message = "邮箱长度不能超过 128")
        String username,

        @Size(max = 64, message = "授权码长度不能超过 64")
        String authCode,

        @Min(value = 10, message = "重发间隔至少 10 秒")
        @Max(value = 3600, message = "重发间隔最多 3600 秒")
        long resendIntervalSeconds,

        @Min(value = 60, message = "验证码有效期至少 60 秒")
        @Max(value = 3600, message = "验证码有效期最多 3600 秒")
        long codeTtlSeconds
) {
}
