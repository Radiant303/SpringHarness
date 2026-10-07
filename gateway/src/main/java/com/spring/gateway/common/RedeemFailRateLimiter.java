package com.spring.gateway.common;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.stereotype.Component;

import java.util.List;

/**
 * 兑换失败限流器：Redis 令牌桶，每账号每分钟最多容忍 {@link #CAPACITY} 次兑换失败，
 * 防暴力枚举兑换码。
 *
 * <p>Redis 抖动时 fail-open：放行并告警。
 *
 * @author hanbing
 * @since 2026-10-07
 */
@Component
public class RedeemFailRateLimiter {

    private static final Logger log = LoggerFactory.getLogger(RedeemFailRateLimiter.class);

    /** 桶 key 前缀，后缀为用户 ID。 */
    private static final String KEY_PREFIX = "redeem:fail:bucket:";

    /** 桶容量 = 每窗口允许的最大失败次数。 */
    private static final long CAPACITY = 10;

    /** 每窗口补充的令牌数（与容量相同）。 */
    private static final long REFILL_PER_WINDOW = 10;

    /** 窗口时长（毫秒）。 */
    private static final long WINDOW_MS = 60_000;

    /**
     * 令牌桶原子操作。KEYS[1]=桶 key；ARGV=容量、每窗口补充数、窗口毫秒、本次扣减数（0=只探查）、当前毫秒。
     * 返回 1=有余量/扣减成功，0=桶空。
     *
     * <p>时间戳由调用方传入（ARGV[5]），脚本行为确定可重放。
     * key TTL = 一个窗口：闲置一个窗口后桶天然回满，到期删除与回满等价。
     */
    private static final DefaultRedisScript<Long> TRY_ACQUIRE = new DefaultRedisScript<>("""
            local capacity = tonumber(ARGV[1])
            local refillPerMs = tonumber(ARGV[2]) / tonumber(ARGV[3])
            local requested = tonumber(ARGV[4])
            local now = tonumber(ARGV[5])
            local data = redis.call('HMGET', KEYS[1], 'tokens', 'ts')
            local tokens = tonumber(data[1])
            local ts = tonumber(data[2])
            if tokens == nil or ts == nil then
              tokens = capacity
              ts = now
            end
            tokens = math.min(capacity, tokens + (now - ts) * refillPerMs)
            local allowed
            if requested == 0 then
              allowed = (tokens >= 1) and 1 or 0
            elseif tokens >= requested then
              tokens = tokens - requested
              allowed = 1
            else
              allowed = 0
            end
            redis.call('HMSET', KEYS[1], 'tokens', tokens, 'ts', now)
            redis.call('PEXPIRE', KEYS[1], tonumber(ARGV[3]))
            return allowed
            """, Long.class);

    private final StringRedisTemplate redis;

    /**
     * @param redis Redis 操作模板
     */
    public RedeemFailRateLimiter(StringRedisTemplate redis) {
        this.redis = redis;
    }

    /**
     * 进入兑换前探查：桶内是否还有失败余量。
     *
     * @param userId 用户 ID
     * @return false 表示失败余量已耗尽，应拒绝
     */
    public boolean tryEnter(long userId) {
        return acquire(userId, 0);
    }

    /**
     * 记录一次兑换失败。
     *
     * @param userId 用户 ID
     */
    public void recordFailure(long userId) {
        acquire(userId, 1);
    }

    /**
     * 兑换成功清零：删 key，下次失败从满桶重新计数。
     *
     * @param userId 用户 ID
     */
    public void reset(long userId) {
        try {
            redis.delete(key(userId));
        } catch (RuntimeException e) {
            log.warn("兑换限流桶清零失败（fail-open）: userId={} err={}", userId, e.getMessage());
        }
    }

    /** 执行令牌桶脚本；Redis 异常时 fail-open 返回 true。 */
    private boolean acquire(long userId, long permits) {
        try {
            Long allowed = redis.execute(TRY_ACQUIRE, List.of(key(userId)),
                    String.valueOf(CAPACITY), String.valueOf(REFILL_PER_WINDOW),
                    String.valueOf(WINDOW_MS), String.valueOf(permits),
                    String.valueOf(System.currentTimeMillis()));
            return allowed == null || allowed == 1;
        } catch (RuntimeException e) {
            log.warn("兑换限流桶访问失败（fail-open）: userId={} err={}", userId, e.getMessage());
            return true;
        }
    }

    private static String key(long userId) {
        return KEY_PREFIX + userId;
    }
}
