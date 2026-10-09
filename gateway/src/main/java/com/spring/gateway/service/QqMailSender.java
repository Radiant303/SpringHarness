package com.spring.gateway.service;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Component;

import java.io.UnsupportedEncodingException;
import java.util.Properties;

/**
 * QQ 邮箱 SMTP 发信器。
 *
 * <p>账号与授权码存数据库（即改即生效），所以不走 spring.mail.* 自动装配，
 * 每次发信按传入参数现场构建 {@link JavaMailSenderImpl}（发码已被限流，频率极低，无需缓存连接）。
 *
 * @author hanbing
 * @since 2026-10-09
 */
@Component
public class QqMailSender {

    /** QQ 邮箱 SMTP 主机（SSL 465）。 */
    private static final String SMTP_HOST = "smtp.qq.com";
    private static final int SMTP_PORT = 465;

    /**
     * 发送纯文本邮件
     *
     * @param from     发件 QQ 邮箱（SMTP 登录账号；QQ 要求 From 与登录账号一致）
     * @param authCode SMTP 授权码（非 QQ 密码）
     * @param to       收件邮箱
     * @param subject  主题
     * @param text     正文（纯文本）
     * @throws MailSendException 发送失败（认证失败、网络错误等）
     */
    public void send(String from, String authCode, String to, String subject, String text) {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost(SMTP_HOST);
        sender.setPort(SMTP_PORT);
        sender.setUsername(from);
        sender.setPassword(authCode);
        Properties props = sender.getJavaMailProperties();
        props.put("mail.smtp.auth", "true");
        props.put("mail.smtp.ssl.enable", "true");
        try {
            MimeMessage message = sender.createMimeMessage();
            MimeMessageHelper helper = new MimeMessageHelper(message, false, "UTF-8");
            helper.setFrom(from, "Spring Harness");
            helper.setTo(to);
            helper.setSubject(subject);
            helper.setText(text, false);
            sender.send(message);
        } catch (MessagingException | UnsupportedEncodingException | MailException e) {
            throw new MailSendException(e);
        }
    }

    /** 发信失败：包装 checked 异常，由调用方决定清理与对外文案。 */
    public static class MailSendException extends RuntimeException {
        public MailSendException(Throwable cause) {
            super(cause);
        }
    }
}
