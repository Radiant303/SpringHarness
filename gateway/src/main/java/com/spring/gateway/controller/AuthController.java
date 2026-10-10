package com.spring.gateway.controller;

import com.spring.gateway.common.Result;
import com.spring.gateway.dto.LoginRequest;
import com.spring.gateway.dto.RegisterRequest;
import com.spring.gateway.dto.ResetPasswordRequest;
import com.spring.gateway.dto.SendCodeRequest;
import com.spring.gateway.dto.TokenResponse;
import com.spring.gateway.dto.UserResponse;
import com.spring.gateway.service.AuthService;
import com.spring.gateway.service.MailCodeService;
import com.spring.gateway.service.SystemSettingService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

/**
 * 认证接口：注册与登录。
 *
 * @author hanbing
 * @since 2026-09-26
 */
@RestController
@RequestMapping("/api/auth")
@RequiredArgsConstructor
public class AuthController {

    private final AuthService authService;
    private final SystemSettingService systemSettingService;

    /**
     * 发送邮箱验证码；同一邮箱在重发间隔内只能发一次。
     * scene=register（默认）要求邮箱未被注册；scene=reset 要求邮箱已注册。
     *
     * @param req 发送请求
     * @return resendAfterSeconds：重发间隔秒数（前端据此倒计时）
     */
    @PostMapping("/send-code")
    public Result<Map<String, Long>> sendCode(@Valid @RequestBody SendCodeRequest req) {
        MailCodeService.Scene scene = "reset".equals(req.scene())
                ? MailCodeService.Scene.RESET : MailCodeService.Scene.REGISTER;
        long resendAfterSeconds = authService.sendSceneCode(req.email(), scene);
        return Result.ok(Map.of("resendAfterSeconds", resendAfterSeconds));
    }

    /**
     * 邮箱验证码重置密码
     *
     * @param req 重置请求
     * @return 空数据返回体
     */
    @PostMapping("/reset-password")
    public Result<Void> resetPassword(@Valid @RequestBody ResetPasswordRequest req) {
        authService.resetPassword(req);
        return Result.ok(null);
    }

    /**
     * 注册页公开配置（无需登录）：是否要求邮箱验证码
     *
     * @return mailVerify：true = 注册必须携带邮箱验证码
     */
    @GetMapping("/register-config")
    public Result<Map<String, Boolean>> registerConfig() {
        return Result.ok(Map.of("mailVerify", systemSettingService.isMailRegisterEnabled()));
    }

    /**
     * 用户注册
     *
     * @param req 注册请求
     * @return 用户信息
     */
    @PostMapping("/register")
    public Result<UserResponse> register(@Valid @RequestBody RegisterRequest req) {
        return Result.ok(authService.register(req));
    }

    /**
     * 用户登录
     *
     * @param req 登录请求
     * @return token
     */
    @PostMapping("/login")
    public Result<TokenResponse> login(@Valid @RequestBody LoginRequest req) {
        return Result.ok(authService.login(req));
    }
}
