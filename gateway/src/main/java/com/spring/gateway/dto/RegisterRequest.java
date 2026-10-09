package com.spring.gateway.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

/**
 * 注册请求。用户名长度 2~64，密码至少 6 位。
 *
 * <p>邮箱与验证码是否必填由系统设置 mail.register_enabled 决定：
 * 开启时强制校验；关闭时忽略这两个字段。
 *
 * @author hanbing
 * @since 2026-09-26
 * @param username 用户名，长度 2~64
 * @param password 密码，至少 6 位
 * @param email    接收验证码的邮箱（QQ 邮箱），开启邮箱验证码注册时必填
 * @param code     6 位邮箱验证码，开启邮箱验证码注册时必填
 */
public record RegisterRequest(
        @NotBlank(message = "用户名不能为空")
        @Size(min = 2, max = 64, message = "用户名长度需 2~64")
        String username,

        @NotBlank(message = "密码不能为空")
        @Size(min = 6, message = "密码至少 6 位")
        String password,

        @Size(max = 128, message = "邮箱长度不能超过 128")
        String email,

        @Size(max = 6, message = "验证码为 6 位数字")
        String code
) {
}
