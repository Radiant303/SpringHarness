package com.spring.gateway.common;

import jakarta.annotation.PostConstruct;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.RedisConnectionFailureException;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

/**
 * workerId 分配器。实例启动时通过 Redis 的 INCR 命令获取全局递增序号，再对 1024 取模作为 workerId。
 * INCR 为原子操作，并发启动不会分配到重复序号。Redis 不可用时抛出异常使应用启动失败。
 *
 * @author hanbing
 * @since 2026-09-25
 */
@Component
public class WorkerIdAllocator {

    private static final Logger log = LoggerFactory.getLogger(WorkerIdAllocator.class);
    private static final String KEY = "snowflake:worker:seq";
    private static final long WORKER_SLOTS = 1024L;

    private final StringRedisTemplate redis;

    private long workerId = -1L;

    /**
     * @param redis Redis 操作模板
     */
    public WorkerIdAllocator(StringRedisTemplate redis) {
        this.redis = redis;
    }

    /**
     * 分配本实例的 workerId，由 Spring 在依赖注入完成后、对外提供服务前回调
     */
    @PostConstruct
    void allocate() {
        Long seq;
        try {
            seq = redis.opsForValue().increment(KEY);
        } catch (RedisConnectionFailureException e) {
            throw new IllegalStateException("Redis 不可用，无法分配 workerId，服务拒绝启动", e);
        }
        if (seq == null) {
            throw new IllegalStateException("Redis 未返回 workerId 序号，服务拒绝启动");
        }
        // 序号从 0 开始分配；领号次数超过 1024 后序号回绕
        this.workerId = Math.floorMod(seq - 1, WORKER_SLOTS);
        log.info("雪花 workerId 分配成功: workerId={}, seq={}", workerId, seq);
    }

    /**
     * @return 本实例的 workerId
     */
    public long getWorkerId() {
        return workerId;
    }
}
