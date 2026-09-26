package com.spring.gateway.common;

import io.jsonwebtoken.Claims;
import io.jsonwebtoken.JwtException;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import javax.crypto.SecretKey;
import java.nio.charset.StandardCharsets;
import java.util.Date;

/**
 * JWT 工具类，提供 token 签发与校验能力。
 * <p>claims 格式、签名密钥与 Python 验签侧存在跨服务契约，修改需两侧同步。</p>
 *
 * @author hanbing
 * @since 2026-09-26
 */
@Component
public class JwtUtils {

    private final SecretKey key;
    private final long expireMillis;

    /**
     * @param secret        HMAC 密钥，长度不少于 32 字节（RFC 7518）
     * @param expireMinutes token 有效期，单位分钟
     */
    public JwtUtils(@Value("${app.jwt-secret}") String secret,
                    @Value("${app.jwt-expire-minutes:10080}") long expireMinutes) {
        this.key = Keys.hmacShaKeyFor(secret.getBytes(StandardCharsets.UTF_8));
        this.expireMillis = expireMinutes * 60_000L;
    }

    /**
     * 签发 token
     *
     * @param userId   用户 ID
     * @param username 用户名
     * @return JWT 字符串
     */
    public String createToken(long userId, String username) {
        return Jwts.builder()
                .subject(String.valueOf(userId))
                .claim("username", username)
                .expiration(new Date(System.currentTimeMillis() + expireMillis))
                .signWith(key)
                .compact();
    }

    /**
     * 验签并解析用户 ID
     *
     * @param token JWT 字符串
     * @return 用户 ID
     */
    public Long parseUserId(String token) {
        try {
            Claims claims = Jwts.parser()
                    .verifyWith(key)
                    .build()
                    .parseSignedClaims(token)
                    .getPayload();
            return Long.parseLong(claims.getSubject());
        } catch (JwtException | IllegalArgumentException e) {
            return null;
        }
    }
}
