package com.spring.gateway.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

/**
 * 已登录用户修改密码请求（双模式，由站长开关决定）：
 * 开启邮箱验证码功能 → 必须带 code（验证码发往绑定邮箱）；
 * 未开启 → 必须带 oldPassword。服务端按开关强制校验，前端传哪个不作数。
 *
 * @author hanbing
 * @since 2026-10-10
 * @param oldPassword 旧密码（未开启邮箱功能时必填）
 * @param code        6 位邮箱验证码（开启邮箱功能时必填，重置场景码）
 * @param newPassword 新密码，至少 6 位
 */
public record ChangePasswordRequest(
        String oldPassword,

        @Pattern(regexp = "\\d{6}", message = "验证码为 6 位数字")
        String code,

        @NotBlank(message = "新密码不能为空")
        @Size(min = 6, message = "密码至少 6 位")
        String newPassword
) {
}
