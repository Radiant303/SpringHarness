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

    /** 设置键：预扣预估的缓存命中输入 tokens。 */
    public static final String KEY_BILLING_EST_CACHE_READ_TOKENS = "billing.est_cache_read_tokens";

    /** 设置键：预扣预估的无缓存输入 tokens。 */
    public static final String KEY_BILLING_EST_INPUT_TOKENS = "billing.est_input_tokens";

    /** 设置键：预扣预估的输出 tokens。 */
    public static final String KEY_BILLING_EST_OUTPUT_TOKENS = "billing.est_output_tokens";

    /** 设置键：是否开启 QQ 邮箱验证码注册（"true"/"false"）。 */
    public static final String KEY_MAIL_REGISTER_ENABLED = "mail.register_enabled";

    /** 设置键：发件 QQ 邮箱（SMTP 登录账号，From 必须与之一致）。 */
    public static final String KEY_MAIL_USERNAME = "mail.username";

    /** 设置键：QQ 邮箱 SMTP 授权码（敏感：接口只写不读，GET 只回"是否已配置"）。 */
    public static final String KEY_MAIL_AUTH_CODE = "mail.auth_code";

    /** 设置键：同一邮箱重发验证码的最小间隔（秒，十进制数字串）。 */
    public static final String KEY_MAIL_RESEND_INTERVAL_SECONDS = "mail.resend_interval_seconds";

    /** 设置键：验证码有效期（秒，十进制数字串）。 */
    public static final String KEY_MAIL_CODE_TTL_SECONDS = "mail.code_ttl_seconds";

    /** 设置键，主键（值由代码固定，手动赋值）。 */
    @TableId(type = IdType.INPUT)
    private String settingKey;

    /** 设置值。 */
    private String settingValue;

    /** 更新时间（UTC）。 */
    private LocalDateTime updatedAt;
}
