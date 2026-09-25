package com.spring.gateway.common;

import java.util.function.LongSupplier;

/**
 * 雪花 ID 生成器。64 位布局：
 * <pre>
 * | 1 位符号(恒0) | 41 位毫秒时间戳(相对自定义纪元) | 10 位 workerId | 12 位序列号 |
 * </pre>
 * 单机每毫秒最多 4096 个号；41 位时间戳从 2024-01-01 起可撑约 69 年。
 * 单实例靠 synchronized 保证线程安全，多实例靠不同 workerId 保证不撞号。
 */
public class SnowflakeIdGenerator {

    /** 自定义纪元：2024-01-01T00:00:00Z */
    public static final long EPOCH = 1704067200000L;

    static final long WORKER_ID_BITS = 10L;
    static final long SEQUENCE_BITS = 12L;
    static final long MAX_WORKER_ID = (1L << WORKER_ID_BITS) - 1;   // 1023
    static final long MAX_SEQUENCE = (1L << SEQUENCE_BITS) - 1;     // 4095
    static final long WORKER_ID_SHIFT = SEQUENCE_BITS;              // 12
    static final long TIMESTAMP_SHIFT = SEQUENCE_BITS + WORKER_ID_BITS; // 22

    /** 时钟回拨容忍上限：≤5ms 自旋等待追平，>5ms 直接抛异常（NTP 大幅校时多半出事了） */
    static final long MAX_BACKWARD_MS = 5L;

    private final long workerId;
    private final LongSupplier clock;

    private long lastTimestamp = -1L;
    private long sequence = 0L;

    public SnowflakeIdGenerator(long workerId) {
        this(workerId, System::currentTimeMillis);
    }

    public SnowflakeIdGenerator(long workerId, LongSupplier clock) {
        if (workerId < 0 || workerId > MAX_WORKER_ID) {
            throw new IllegalArgumentException("workerId 必须在 0~" + MAX_WORKER_ID + " 之间，收到: " + workerId);
        }
        this.workerId = workerId;
        this.clock = clock;
    }

    public synchronized long nextId() {
        long timestamp = clock.getAsLong();

        if (timestamp < lastTimestamp) {
            long backward = lastTimestamp - timestamp;
            if (backward > MAX_BACKWARD_MS) {
                throw new IllegalStateException("时钟回拨 " + backward + "ms，超过容忍上限，拒绝发号");
            }
            do {
                Thread.onSpinWait();
                timestamp = clock.getAsLong();
            } while (timestamp < lastTimestamp);
        }

        if (timestamp == lastTimestamp) {
            sequence = (sequence + 1) & MAX_SEQUENCE;
            if (sequence == 0) {
                // 本毫秒 4096 个号发完了，等下一毫秒
                timestamp = waitNextMillis(lastTimestamp);
            }
        } else {
            sequence = 0L;
        }

        lastTimestamp = timestamp;

        return ((timestamp - EPOCH) << TIMESTAMP_SHIFT)
                | (workerId << WORKER_ID_SHIFT)
                | sequence;
    }

    private long waitNextMillis(long ts) {
        long now = clock.getAsLong();
        while (now <= ts) {
            Thread.onSpinWait();
            now = clock.getAsLong();
        }
        return now;
    }
}
