package com.spring.gateway.controller;

import com.spring.gateway.common.Result;
import com.spring.gateway.dto.LoginRequest;
import com.spring.gateway.dto.RegisterRequest;
import com.spring.gateway.dto.TokenResponse;
import com.spring.gateway.dto.UserResponse;
import com.spring.gateway.service.AuthService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

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
