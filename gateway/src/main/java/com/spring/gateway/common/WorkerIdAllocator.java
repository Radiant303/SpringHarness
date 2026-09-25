package com.spring.gateway.common;

import jakarta.annotation.PostConstruct;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.redis.RedisConnectionFailureException;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

/**
 * 启动时从 Redis 申请本实例的 workerId：INCR 一个全局计数器后对 1024 取模。
 * Redis 不可用时拒绝启动
 */
@Component
public class WorkerIdAllocator {

    private static final Logger log = LoggerFactory.getLogger(WorkerIdAllocator.class);
    private static final String KEY = "snowflake:worker:seq";
    private static final long WORKER_SLOTS = 1024L;

    private final StringRedisTemplate redis;

    private long workerId = -1L;

    public WorkerIdAllocator(StringRedisTemplate redis) {
        this.redis = redis;
    }

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
        // 第 1 个实例拿 0；超过 1024 个实例会回绕，届时需要引入租约回收
        this.workerId = Math.floorMod(seq - 1, WORKER_SLOTS);
        log.info("雪花 workerId 分配成功: workerId={}, seq={}", workerId, seq);
    }

    public long getWorkerId() {
        return workerId;
    }
}
