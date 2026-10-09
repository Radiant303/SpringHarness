package com.spring.gateway.service;

import com.spring.gateway.entity.SystemSetting;
import com.spring.gateway.mapper.SystemSettingMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.time.ZoneOffset;

/**
 * 运行时系统设置：直读直写 system_settings 小表，不缓存（改动频率极低，读取都在管理路径上）。
 *
 * @author hanbing
 * @since 2026-10-05
 */
@Service
@RequiredArgsConstructor
public class SystemSettingService {

    private final SystemSettingMapper systemSettingMapper;

    /**
     * 读布尔设置；键不存在时返回默认值
     *
     * @param key          设置键
     * @param defaultValue 键缺失时的默认值
     * @return 设置值
     */
    public boolean getBool(String key, boolean defaultValue) {
        SystemSetting row = systemSettingMapper.selectById(key);
        if (row == null) {
            return defaultValue;
        }
        return Boolean.parseBoolean(row.getSettingValue());
    }

    /**
     * 是否开放注册；默认开放
     *
     * @return true = 开放
     */
    public boolean isRegistrationOpen() {
        return getBool(SystemSetting.KEY_REGISTRATION_OPEN, true);
    }

    /**
     * 读长整型设置；键不存在或值无法解析时返回默认值
     *
     * @param key          设置键
     * @param defaultValue 键缺失或值非法时的默认值
     * @return 设置值
     */
    public long getLong(String key, long defaultValue) {
        SystemSetting row = systemSettingMapper.selectById(key);
        if (row == null) {
            return defaultValue;
        }
        try {
            return Long.parseLong(row.getSettingValue().trim());
        } catch (NumberFormatException e) {
            return defaultValue;
        }
    }

    /**
     * 全局单工作区上限（字节）；默认 20MB
     *
     * @return 上限字节数
     */
    public long getWorkMaxBytes() {
        return getLong(SystemSetting.KEY_WORK_MAX_BYTES, 20971520L);
    }

    /**
     * 读字符串设置；键不存在时返回默认值
     *
     * @param key          设置键
     * @param defaultValue 键缺失时的默认值
     * @return 设置值
     */
    public String getString(String key, String defaultValue) {
        SystemSetting row = systemSettingMapper.selectById(key);
        return row == null || row.getSettingValue() == null ? defaultValue : row.getSettingValue().trim();
    }

    /**
     * 是否开启 QQ 邮箱验证码注册；默认关闭
     *
     * @return true = 注册必须携带邮箱验证码
     */
    public boolean isMailRegisterEnabled() {
        return getBool(SystemSetting.KEY_MAIL_REGISTER_ENABLED, false);
    }

    /**
     * 发件 QQ 邮箱；默认空串（未配置）
     *
     * @return 发件邮箱
     */
    public String getMailUsername() {
        return getString(SystemSetting.KEY_MAIL_USERNAME, "");
    }

    /**
     * QQ 邮箱 SMTP 授权码；默认空串（未配置）
     *
     * @return 授权码
     */
    public String getMailAuthCode() {
        return getString(SystemSetting.KEY_MAIL_AUTH_CODE, "");
    }

    /**
     * 同一邮箱重发验证码的最小间隔（秒）；默认 60
     *
     * @return 间隔秒数
     */
    public long getMailResendIntervalSeconds() {
        return getLong(SystemSetting.KEY_MAIL_RESEND_INTERVAL_SECONDS, 60L);
    }

    /**
     * 验证码有效期（秒）；默认 300
     *
     * @return 有效期秒数
     */
    public long getMailCodeTtlSeconds() {
        return getLong(SystemSetting.KEY_MAIL_CODE_TTL_SECONDS, 300L);
    }

    /**
     * 写设置（upsert：存在更新值与 updated_at，不存在插入）
     *
     * @param key   设置键
     * @param value 设置值
     */
    public void set(String key, String value) {
        SystemSetting row = new SystemSetting();
        row.setSettingKey(key);
        row.setSettingValue(value);
        row.setUpdatedAt(LocalDateTime.now(ZoneOffset.UTC));
        systemSettingMapper.insertOrUpdate(row);
    }
}
