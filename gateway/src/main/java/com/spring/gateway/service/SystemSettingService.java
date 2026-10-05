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
     * 读布尔设置；键不存在时返回默认值（迁移未播种或键被误删时按默认行为运行）
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
