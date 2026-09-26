package com.spring.gateway.common;

import java.util.function.LongSupplier;

/**
 * 雪花 ID 生成器。64 位布局：1 位符号位（固定为 0）+ 41 位毫秒时间戳（相对自定义纪元）
 * + 10 位机器标识 + 12 位序列号。
 * 单实例内通过 synchronized 保证线程安全；多实例之间通过不同的 workerId 保证 ID 唯一。
 *
 * @author hanbing
 * @since 2026-09-25
 */
public class SnowflakeIdGenerator {

    /**
     * 自定义纪元：2024-01-01T00:00:00Z。41 位时间戳自该时刻起约可使用 69 年
     */
    public static final long EPOCH = 1704067200000L;

    static final long WORKER_ID_BITS = 10L;
    static final long SEQUENCE_BITS = 12L;
    static final long MAX_WORKER_ID = (1L << WORKER_ID_BITS) - 1;
    static final long MAX_SEQUENCE = (1L << SEQUENCE_BITS) - 1;
    static final long WORKER_ID_SHIFT = SEQUENCE_BITS;
    static final long TIMESTAMP_SHIFT = SEQUENCE_BITS + WORKER_ID_BITS;

    /**
     * 允许的最大时钟回拨毫秒数。回拨不超过该值时自旋等待时钟追平；
     * 超过该值时拒绝发号，避免产生重复 ID
     */
    static final long MAX_BACKWARD_MS = 5L;

    private final long workerId;
    private final LongSupplier clock;

    private long lastTimestamp = -1L;
    private long sequence = 0L;

    /**
     * @param workerId 机器标识，取值范围 0~1023
     */
    public SnowflakeIdGenerator(long workerId) {
        this(workerId, System::currentTimeMillis);
    }

    /**
     * @param workerId 机器标识，取值范围 0~1023
     * @param clock    时钟源
     */
    public SnowflakeIdGenerator(long workerId, LongSupplier clock) {
        if (workerId < 0 || workerId > MAX_WORKER_ID) {
            throw new IllegalArgumentException("workerId 必须在 0~" + MAX_WORKER_ID + " 之间，收到: " + workerId);
        }
        this.workerId = workerId;
        this.clock = clock;
    }

    /**
     * 生成下一个全局唯一 ID
     *
     * @return 64 位雪花 ID
     */
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
                // 序列号溢出表示当前毫秒的号段已用完，等待进入下一毫秒
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

    /**
     * 自旋等待，直到时钟超过指定毫秒
     *
     * @param ts 参考毫秒时间戳
     * @return 大于 ts 的当前毫秒时间戳
     */
    private long waitNextMillis(long ts) {
        long now = clock.getAsLong();
        while (now <= ts) {
            Thread.onSpinWait();
            now = clock.getAsLong();
        }
        return now;
    }
}
