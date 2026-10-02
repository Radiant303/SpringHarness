package com.spring.gateway.service;

import com.spring.gateway.config.RabbitConfig;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.amqp.core.QueueInformation;
import org.springframework.amqp.rabbit.core.RabbitAdmin;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 队列深度监控：被动声明拿到各队列的堆积量，非零即告警日志；
 * 同时供 MqAdminController 查询。被动声明不会创建队列，只读元数据。
 *
 * @author hanbing
 * @since 2026-10-02
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class MqMonitor {

    /** 监控的全部队列：三个业务队列 + 三个死信队列 */
    private static final List<String> QUEUES = List.of(
            RabbitConfig.QUEUE_DISPATCH, RabbitConfig.QUEUE_CANCEL, RabbitConfig.QUEUE_LIFECYCLE,
            RabbitConfig.QUEUE_DISPATCH_DLQ, RabbitConfig.QUEUE_CANCEL_DLQ, RabbitConfig.QUEUE_LIFECYCLE_DLQ);

    private final RabbitAdmin rabbitAdmin;

    /**
     * 各队列当前堆积量；队列不存在（未声明过）时值为 null
     */
    public Map<String, Long> queueDepths() {
        Map<String, Long> depths = new LinkedHashMap<>();
        for (String queue : QUEUES) {
            // 4.1 起用类型化的 getQueueInfo；旧 getQueueProperties 的键是 Object 单例，按字符串取不到值
            QueueInformation info = rabbitAdmin.getQueueInfo(queue);
            depths.put(queue, info == null ? null : info.getMessageCount());
        }
        return depths;
    }

    /** 每分钟巡检：任何队列有堆积都记 warn（DLQ 非零时 DlqListener 通常已先告警） */
    @Scheduled(fixedDelay = 60_000)
    public void inspect() {
        try {
            queueDepths().forEach((queue, depth) -> {
                if (depth != null && depth > 0) {
                    log.warn("MQ 队列有堆积: {} depth={}", queue, depth);
                }
            });
        } catch (Exception e) {
            log.warn("MQ 队列巡检失败: {}", e.getMessage());
        }
    }
}
