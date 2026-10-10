package com.spring.gateway.controller;

import com.spring.gateway.common.AuthInterceptor;
import com.spring.gateway.common.Result;
import com.spring.gateway.dto.BindEmailRequest;
import com.spring.gateway.dto.ChangePasswordRequest;
import com.spring.gateway.entity.User;
import com.spring.gateway.mapper.UserMapper;
import com.spring.gateway.service.AuthService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.HashMap;
import java.util.Map;

/**
 * 当前登录用户的账户接口：资料查询与邮箱验证码改密码。
 *
 * @author hanbing
 * @since 2026-10-10
 */
@RestController
@RequestMapping("/api/account")
@RequiredArgsConstructor
public class AccountController {

    private final AuthService authService;
    private final UserMapper userMapper;

    /**
     * 当前用户资料（用户名 + 绑定邮箱）
     *
     * @param userId 当前用户 ID
     * @return 用户名与邮箱（未绑定为 null）
     */
    @GetMapping("/me")
    public Result<Map<String, Object>> me(@RequestAttribute(AuthInterceptor.ATTR_USER_ID) Long userId) {
        User user = userMapper.selectById(userId);
        Map<String, Object> data = new HashMap<>();
        data.put("username", user.getUsername());
        data.put("email", user.getEmail());
        return Result.ok(data);
    }

    /**
     * 给待绑定邮箱发验证码（绑定/换绑通用；邮箱不能被其他账号占用）
     *
     * @param userId 当前用户 ID
     * @param req    待绑定邮箱
     * @return resendAfterSeconds：重发间隔秒数（前端据此倒计时）
     */
    @PostMapping("/send-bind-code")
    public Result<Map<String, Long>> sendBindCode(@RequestAttribute(AuthInterceptor.ATTR_USER_ID) Long userId,
                                                  @Valid @RequestBody BindEmailRequest req) {
        return Result.ok(Map.of("resendAfterSeconds", authService.sendBindCode(userId, req.email())));
    }

    /**
     * 凭验证码绑定/换绑邮箱
     *
     * @param userId 当前用户 ID
     * @param req    邮箱与验证码
     * @return 空数据返回体
     */
    @PostMapping("/bind-email")
    public Result<Void> bindEmail(@RequestAttribute(AuthInterceptor.ATTR_USER_ID) Long userId,
                                  @Valid @RequestBody BindEmailRequest req) {
        authService.bindEmail(userId, req.email(), req.code());
        return Result.ok(null);
    }

    /**
     * 给当前账号的绑定邮箱发验证码（开启邮箱功能时改密码用）
     *
     * @param userId 当前用户 ID
     * @return resendAfterSeconds：重发间隔秒数（前端据此倒计时）
     */
    @PostMapping("/send-code")
    public Result<Map<String, Long>> sendCode(@RequestAttribute(AuthInterceptor.ATTR_USER_ID) Long userId) {
        return Result.ok(Map.of("resendAfterSeconds", authService.sendMyCode(userId)));
    }

    /**
     * 修改密码（双模式：开启邮箱功能凭邮箱验证码，未开启校验旧密码）
     *
     * @param userId 当前用户 ID
     * @param req    旧密码 / 验证码 / 新密码
     * @return 空数据返回体
     */
    @PostMapping("/change-password")
    public Result<Void> changePassword(@RequestAttribute(AuthInterceptor.ATTR_USER_ID) Long userId,
                                       @Valid @RequestBody ChangePasswordRequest req) {
        authService.changePassword(userId, req);
        return Result.ok(null);
    }
}
