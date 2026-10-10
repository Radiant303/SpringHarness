package com.spring.gateway.controller;

import com.spring.gateway.common.RequiresOwner;
import com.spring.gateway.common.Result;
import com.spring.gateway.dto.AdminBillingEstRequest;
import com.spring.gateway.dto.AdminMailSettingsRequest;
import com.spring.gateway.dto.AdminRegistrationRequest;
import com.spring.gateway.dto.AdminWorkMaxBytesRequest;
import com.spring.gateway.common.BizException;
import com.spring.gateway.entity.SystemSetting;
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
     * @return 设置快照（registrationOpen、workMaxBytes、billingEst* 三档位、mail* 邮箱验证码注册；
     *         授权码敏感不回值，只回 mailAuthCodeConfigured 表示是否已配置）
     */
    @GetMapping
    public Result<Map<String, Object>> get() {
        return Result.ok(Map.of(
                "registrationOpen", systemSettingService.isRegistrationOpen(),
                "workMaxBytes", systemSettingService.getWorkMaxBytes(),
                "billingEstCacheReadTokens", systemSettingService.getLong(
                        SystemSetting.KEY_BILLING_EST_CACHE_READ_TOKENS, 90000L),
                "billingEstInputTokens", systemSettingService.getLong(
                        SystemSetting.KEY_BILLING_EST_INPUT_TOKENS, 10000L),
                "billingEstOutputTokens", systemSettingService.getLong(
                        SystemSetting.KEY_BILLING_EST_OUTPUT_TOKENS, 20000L),
                "mailRegisterEnabled", systemSettingService.isMailRegisterEnabled(),
                "mailUsername", systemSettingService.getMailUsername(),
                "mailAuthCodeConfigured", !systemSettingService.getMailAuthCode().isBlank(),
                "mailResendIntervalSeconds", systemSettingService.getMailResendIntervalSeconds(),
                "mailCodeTtlSeconds", systemSettingService.getMailCodeTtlSeconds()));
    }

    /**
     * 设置注册开关
     *
     * @param req 开关
     * @return 空数据返回体
     */
    @RequiresOwner(message = "仅站长可修改系统设置")
    @PostMapping("/registration")
    public Result<Void> setRegistration(@Valid @RequestBody AdminRegistrationRequest req) {
        systemSettingService.set(SystemSetting.KEY_REGISTRATION_OPEN, String.valueOf(req.open()));
        return Result.ok(null);
    }

    /**
     * 设置全局单工作区上限
     *
     * @param req 上限字节数
     * @return 空数据返回体
     */
    @RequiresOwner(message = "仅站长可修改系统设置")
    @PostMapping("/work-max-bytes")
    public Result<Void> setWorkMaxBytes(@Valid @RequestBody AdminWorkMaxBytesRequest req) {
        systemSettingService.set(SystemSetting.KEY_WORK_MAX_BYTES, String.valueOf(req.bytes()));
        return Result.ok(null);
    }

    /**
     * 配置邮箱验证码注册。username/authCode 留空表示保持不变；
     * 开启时要求最终生效的发件邮箱与授权码都已就绪。
     *
     * @param req 邮箱设置
     * @return 空数据返回体
     */
    @RequiresOwner(message = "仅站长可修改系统设置")
    @PostMapping("/mail")
    public Result<Void> setMail(@Valid @RequestBody AdminMailSettingsRequest req) {
        String username = req.username() == null ? "" : req.username().trim();
        if (!username.isEmpty() && !MailCodeService.isValidEmail(username)) {
            throw new BizException(400, "发件邮箱格式不正确");
        }
        String authCode = req.authCode() == null ? "" : req.authCode().trim();
        // 生效值 = 本次传入优先，否则沿用已存储值
        String effectiveUsername = username.isEmpty() ? systemSettingService.getMailUsername() : username;
        boolean authReady = !authCode.isEmpty() || !systemSettingService.getMailAuthCode().isBlank();
        if (Boolean.TRUE.equals(req.enabled()) && (effectiveUsername.isBlank() || !authReady)) {
            throw new BizException(400, "开启前请先配置发件 QQ 邮箱与 SMTP 授权码");
        }
        systemSettingService.set(SystemSetting.KEY_MAIL_REGISTER_ENABLED, String.valueOf(req.enabled()));
        if (!username.isEmpty()) {
            systemSettingService.set(SystemSetting.KEY_MAIL_USERNAME, effectiveUsername.toLowerCase());
        }
        if (!authCode.isEmpty()) {
            systemSettingService.set(SystemSetting.KEY_MAIL_AUTH_CODE, authCode);
        }
        systemSettingService.set(SystemSetting.KEY_MAIL_RESEND_INTERVAL_SECONDS,
                String.valueOf(req.resendIntervalSeconds()));
        systemSettingService.set(SystemSetting.KEY_MAIL_CODE_TTL_SECONDS, String.valueOf(req.codeTtlSeconds()));
        return Result.ok(null);
    }

    /**
     * 设置预扣预估档位
     *
     * @param req 三档 tokens 数
     * @return 空数据返回体
     */
    @RequiresOwner(message = "仅站长可修改系统设置")
    @PostMapping("/billing-est")
    public Result<Void> setBillingEst(@Valid @RequestBody AdminBillingEstRequest req) {
        systemSettingService.set(SystemSetting.KEY_BILLING_EST_CACHE_READ_TOKENS,
                String.valueOf(req.cacheReadTokens()));
        systemSettingService.set(SystemSetting.KEY_BILLING_EST_INPUT_TOKENS,
                String.valueOf(req.inputTokens()));
        systemSettingService.set(SystemSetting.KEY_BILLING_EST_OUTPUT_TOKENS,
                String.valueOf(req.outputTokens()));
        return Result.ok(null);
    }
}
