package com.spring.gateway.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

/**
 * system_settings 表的实体：运行时系统设置（站长可在后台修改）。
 *
 * @author hanbing
 * @since 2026-10-05
 */
@Data
@TableName("system_settings")
public class SystemSetting {

    /** 设置键：是否开放注册（"true"/"false"）。 */
    public static final String KEY_REGISTRATION_OPEN = "registration_open";

    /** 设置键：全局默认单 work 容量上限（字节，十进制数字串）。 */
    public static final String KEY_WORK_MAX_BYTES = "work_max_bytes";

    /** 设置键，主键（值由代码固定，手动赋值）。 */
    @TableId(type = IdType.INPUT)
    private String settingKey;

    /** 设置值。 */
    private String settingValue;

    /** 更新时间（UTC）。 */
    private LocalDateTime updatedAt;
}
