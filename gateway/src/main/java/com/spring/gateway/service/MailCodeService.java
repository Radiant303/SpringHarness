package com.spring.gateway.service;

import com.spring.gateway.common.BizException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

import java.security.SecureRandom;
import java.time.Duration;
import java.util.regex.Pattern;

/**
 * 注册邮箱验证码：生成、发送（QQ 邮箱 SMTP）与校验。
 *
 * <p>开关与 SMTP 配置都在数据库 system_settings 表（即改即生效）。验证码与重发锁放 Redis，不落库：
 * <ul>
 *   <li>{@code mail:code:{email}} —— 6 位验证码，TTL = mail.code_ttl_seconds</li>
 *   <li>{@code mail:code:lock:{email}} —— 重发锁，SET NX PX 原子抢占，TTL = mail.resend_interval_seconds，
 *       保证同一邮箱一个间隔内只发一次</li>
 * </ul>
 *
 * <p>验证码一次性：校验通过即删除。Redis 不可用时 fail-closed（抛 500），验证码场景不能放行。
 *
 * @author hanbing
 * @since 2026-10-09
 */
@Service
public class MailCodeService {

    private static final Logger log = LoggerFactory.getLogger(MailCodeService.class);

    /** 验证码 key 前缀，后缀为邮箱（小写）。 */
    private static final String CODE_KEY_PREFIX = "mail:code:";

    /** 重发锁 key 前缀，后缀为邮箱（小写）。 */
    private static final String LOCK_KEY_PREFIX = "mail:code:lock:";

    /** 宽松的邮箱格式校验（与前端一致，够用即可，严格校验交给 SMTP 投递）。 */
    private static final Pattern EMAIL_PATTERN = Pattern.compile("^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$");

    private final StringRedisTemplate redis;
    private final QqMailSender mailSender;
    private final SystemSettingService settings;

    /**
     * @param redis      Redis 操作模板
     * @param mailSender QQ 邮箱发信器
     * @param settings   系统设置（开关、SMTP 账号、重发间隔、有效期）
     */
    public MailCodeService(StringRedisTemplate redis, QqMailSender mailSender, SystemSettingService settings) {
        this.redis = redis;
        this.mailSender = mailSender;
        this.settings = settings;
    }

    /**
     * 发送验证码到指定邮箱；同一邮箱在重发间隔内只能发一次
     *
     * @param email 收件邮箱（会被 trim + 转小写归一化）
     * @return 重发间隔秒数（前端据此倒计时）
     * @throws BizException 未开启邮箱注册（403）；邮箱服务未配置（500）；
     *                      发送过于频繁（429）；邮件发送失败（500，此时锁与验证码一并清除，可立即重试）
     */
    public long sendCode(String email) {
        if (!settings.isMailRegisterEnabled()) {
            throw new BizException(403, "当前未开启邮箱验证码注册");
        }
        String from = settings.getMailUsername();
        String authCode = settings.getMailAuthCode();
        if (from.isBlank() || authCode.isBlank()) {
            throw new BizException(500, "邮箱验证码服务未配置，请联系站长");
        }
        String normalized = normalize(email);
        long resendIntervalSeconds = settings.getMailResendIntervalSeconds();
        long codeTtlSeconds = settings.getMailCodeTtlSeconds();
        // SET NX PX：原子抢占重发锁；抢不到说明间隔内已发过
        Boolean acquired = redis.opsForValue().setIfAbsent(
                LOCK_KEY_PREFIX + normalized, "1", Duration.ofSeconds(resendIntervalSeconds));
        if (!Boolean.TRUE.equals(acquired)) {
            throw new BizException(429, "发送过于频繁，请 " + resendIntervalSeconds + " 秒后再试");
        }
        String code = generateCode();
        redis.opsForValue().set(CODE_KEY_PREFIX + normalized, code, Duration.ofSeconds(codeTtlSeconds));
        try {
            mailSender.send(from, authCode, normalized, "【Spring Harness】注册验证码",
                    "您的注册验证码是：" + code + "，" + (codeTtlSeconds / 60) + " 分钟内有效。请勿泄露给他人。");
        } catch (RuntimeException e) {
            // 发信失败：清掉锁与验证码，让用户可以立刻重发，而不是等锁自然过期
            redis.delete(LOCK_KEY_PREFIX + normalized);
            redis.delete(CODE_KEY_PREFIX + normalized);
            log.error("验证码邮件发送失败: email={} err={}", normalized, e.getMessage());
            throw new BizException(500, "验证码发送失败，请稍后再试");
        }
        log.info("注册验证码已发送: email={}", normalized);
        return resendIntervalSeconds;
    }

    /**
     * 校验验证码；校验通过即删除（一次性），不匹配不删（允许输错重试至过期）
     *
     * @param email 邮箱（会被归一化）
     * @param code  用户输入的验证码
     * @throws BizException 验证码错误或已过期（400）
     */
    public void verifyCode(String email, String code) {
        String key = CODE_KEY_PREFIX + normalize(email);
        String stored = redis.opsForValue().get(key);
        if (stored == null || !stored.equals(code)) {
            throw new BizException(400, "验证码错误或已过期");
        }
        redis.delete(key);
    }

    /** 归一化邮箱：去空白 + 小写，保证锁/验证码/唯一索引口径一致。 */
    public static String normalize(String email) {
        return email == null ? "" : email.trim().toLowerCase();
    }

    /** 邮箱格式校验（宽松）。 */
    public static boolean isValidEmail(String email) {
        return EMAIL_PATTERN.matcher(email).matches();
    }

    /** 生成 6 位数字验证码（SecureRandom，避免可预测）。 */
    private static String generateCode() {
        return String.format("%06d", new SecureRandom().nextInt(1_000_000));
    }
}
