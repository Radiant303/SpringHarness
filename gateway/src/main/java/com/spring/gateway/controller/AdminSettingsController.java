package com.spring.gateway.controller;

import com.spring.gateway.common.AuthInterceptor;
import com.spring.gateway.common.BizException;
import com.spring.gateway.common.Result;
import com.spring.gateway.dto.AdminRegistrationRequest;
import com.spring.gateway.entity.SystemSetting;
import com.spring.gateway.entity.User;
import com.spring.gateway.service.SystemSettingService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

/**
 * 系统设置接口：查看对 owner/admin 开放，修改仅站长。
 *
 * @author hanbing
 * @since 2026-10-05
 */
@RestController
@RequestMapping("/api/admin/settings")
@RequiredArgsConstructor
public class AdminSettingsController {

    private final SystemSettingService systemSettingService;

    /**
     * 当前系统设置
     *
     * @return 设置快照（registrationOpen）
     */
    @GetMapping
    public Result<Map<String, Object>> get() {
        return Result.ok(Map.of("registrationOpen", systemSettingService.isRegistrationOpen()));
    }

    /**
     * 设置注册开关（仅站长）
     *
     * @param actorRole 当前用户角色（拦截器注入）
     * @param req       开关
     * @return 空数据返回体
     */
    @PostMapping("/registration")
    public Result<Void> setRegistration(@RequestAttribute(AuthInterceptor.ATTR_USER_ROLE) String actorRole,
                                        @Valid @RequestBody AdminRegistrationRequest req) {
        if (!User.ROLE_OWNER.equals(actorRole)) {
            throw new BizException(403, "仅站长可修改系统设置");
        }
        systemSettingService.set(SystemSetting.KEY_REGISTRATION_OPEN, String.valueOf(req.open()));
        return Result.ok(null);
    }
}
