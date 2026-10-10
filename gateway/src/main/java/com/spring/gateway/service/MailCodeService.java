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
 * <p>开关与 SMTP 配置都在数据库 system_settings 表。验证码与重发锁放 Redis，不落库：
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

    /**
     * HTML 邮件模板（text block 内联在代码里，{{code}}/{{ttlText}} 为占位符）。
     * 设计要点：隐藏 preheader（收件箱预览文案）、药丸验证码容器、深色模式 media query、
     * 全部样式 inline（多数邮件客户端会剥离 &lt;style&gt; 块，深色模式只是渐进增强）、
     * Outlook 桌面版降级为直角灰块但可读性不受影响。
     */
    private static final String HTML_TEMPLATE = """
            <!DOCTYPE html>
            <html lang="zh-CN">
            <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <meta name="color-scheme" content="light dark">
            <meta name="supported-color-schemes" content="light dark">
            <title>安全验证</title>
            <style>
              @media (prefers-color-scheme: dark) {
                .email-body { background-color: #161B22 !important; }
                .pill { background-color: #21262D !important; }
                .title, .code { color: #E6EDF3 !important; }
                .desc { color: #8B949E !important; }
                .hint { color: #6E7681 !important; }
              }
            </style>
            </head>
            <body style="margin: 0; padding: 0; background-color: #FFFFFF; -webkit-font-smoothing: antialiased;">
            <div style="background-color: #FFFFFF; padding: 48px 16px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Inter, sans-serif;">
              <!-- 隐藏 preheader：列表预览时显示 -->
              <div style="display: none; max-height: 0; overflow: hidden; mso-hide: all;">您的验证码是 {{code}}，{{ttlText}}内有效</div>
              <div class="email-body" style="max-width: 420px; margin: 0 auto; box-sizing: border-box;">
                <!-- 标题 -->
                <h2 class="title" style="margin: 0 0 10px; font-size: 18px; font-weight: 600; color: #1F2328; letter-spacing: -0.02em;">安全验证</h2>
                <!-- 说明文字 -->
                <p class="desc" style="margin: 0 0 28px; font-size: 13px; line-height: 1.6; color: #656D76;">您正在进行身份验证，请在 {{ttlText}}内使用以下验证码完成操作：</p>
                <!-- 气泡风格浅灰全圆角药丸容器（Outlook 桌面版降级为直角灰块，可读性不受影响） -->
                <div class="pill" style="background-color: #F4F4F4; border-radius: 9999px; padding: 20px 24px; text-align: center; margin-bottom: 28px;">
                  <span class="code" id="verify-code" aria-label="{{code}}" style="display: inline-block; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 30px; font-weight: 600; letter-spacing: 10px; color: #1F2328; padding-left: 10px; font-feature-settings: 'tnum';">{{code}}</span>
                </div>
                <!-- 底部提示 -->
                <p class="hint" style="margin: 0; font-size: 12px; line-height: 1.5; color: #8C959F;">如非本人操作，请忽略此邮件。</p>
              </div>
            </div>
            </body>
            </html>
            """;

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

    /** 有效期文案：整分钟显示"N 分钟"，否则显示"N 秒"。 */
    private static String ttlText(long ttlSeconds) {
        return ttlSeconds % 60 == 0 ? (ttlSeconds / 60) + " 分钟" : ttlSeconds + " 秒";
    }

    /**
     * 验证码用途。Redis key 按用途分命名空间（mail:code:{scene}:{email}），
     * 防串用——注册码不能拿去重置密码；限流锁按邮箱共享（防骚扰针对的是收件箱）。
     */
    public enum Scene {
        /** 注册验证 */
        REGISTER("register", "注册"),
        /** 重置密码 */
        RESET("reset", "重置密码"),
        /** 绑定邮箱 */
        BIND("bind", "绑定邮箱");

        /** Redis key 片段与文案用词。 */
        private final String keySegment;
        private final String actionText;

        Scene(String keySegment, String actionText) {
            this.keySegment = keySegment;
            this.actionText = actionText;
        }
    }

    /**
     * 发送验证码到指定邮箱；同一邮箱在重发间隔内只能发一次（跨用途共享限流锁）
     *
     * @param email 收件邮箱（会被 trim + 转小写归一化）
     * @param scene 用途（注册 / 重置密码）
     * @return 重发间隔秒数（前端据此倒计时）
     * @throws BizException 未开启邮箱验证码功能（403）；邮箱服务未配置（500）；
     *                      发送过于频繁（429）；邮件发送失败（500，此时锁与验证码一并清除，可立即重试）
     */
    public long sendCode(String email, Scene scene) {
        if (!settings.isMailRegisterEnabled()) {
            throw new BizException(403, "当前未开启邮箱验证码功能");
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
        String codeKey = codeKey(scene, normalized);
        redis.opsForValue().set(codeKey, code, Duration.ofSeconds(codeTtlSeconds));
        // multipart/alternative：纯文本兜底 + HTML 模板，客户端按渲染能力选择
        String ttl = ttlText(codeTtlSeconds);
        String plainText = "您正在" + scene.actionText + "，验证码是：" + code + "，" + ttl + "内有效。请勿泄露给他人。";
        String html = HTML_TEMPLATE.replace("{{code}}", code).replace("{{ttlText}}", ttl);
        try {
            mailSender.send(from, authCode, normalized,
                    "【Spring Harness】" + scene.actionText + "验证码", plainText, html);
        } catch (RuntimeException e) {
            // 发信失败：清掉锁与验证码，让用户可以立刻重发，而不是等锁自然过期
            redis.delete(LOCK_KEY_PREFIX + normalized);
            redis.delete(codeKey);
            log.error("验证码邮件发送失败: email={} scene={} err={}", normalized, scene.keySegment, e.getMessage());
            throw new BizException(500, "验证码发送失败，请稍后再试");
        }
        log.info("验证码已发送: email={} scene={}", normalized, scene.keySegment);
        return resendIntervalSeconds;
    }

    /**
     * 校验验证码；校验通过即删除（一次性），不匹配不删（允许输错重试至过期）
     *
     * @param email 邮箱（会被归一化）
     * @param code  用户输入的验证码
     * @param scene 用途（必须与发送时一致，否则永远不匹配）
     * @throws BizException 验证码错误或已过期（400）
     */
    public void verifyCode(String email, String code, Scene scene) {
        String key = codeKey(scene, normalize(email));
        String stored = redis.opsForValue().get(key);
        if (stored == null || !stored.equals(code)) {
            throw new BizException(400, "验证码错误或已过期");
        }
        redis.delete(key);
    }

    /** 验证码 key：按用途隔离命名空间。 */
    private static String codeKey(Scene scene, String normalizedEmail) {
        return CODE_KEY_PREFIX + scene.keySegment + ":" + normalizedEmail;
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
