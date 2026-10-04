package com.spring.gateway.service;

import com.spring.gateway.config.RabbitConfig;
import lombok.extern.slf4j.Slf4j;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.messaging.handler.annotation.Headers;
import org.springframework.stereotype.Component;

import java.nio.charset.StandardCharsets;
import java.util.Map;

/**
 * 死信队列监听：重试超限或消费异常的消息最终落在这里。
 * 出现 DLQ 消息代表系统有缺陷或数据有问题，必须有人看见，故用 error 级别告警。
 * <p>
 * 监听必须使用不做 JSON 转换的容器工厂：DLQ 消息体可能根本不是 JSON
 * （正是它导致消费失败），若走默认的 Jackson 转换器，转换失败会让告警逻辑无法执行。
 *
 * @author hanbing
 * @since 2026-10-02
 */
@Slf4j
@Component
public class DlqListener {

    @RabbitListener(
            queues = {RabbitConfig.QUEUE_DISPATCH_DLQ, RabbitConfig.QUEUE_CANCEL_DLQ,
                    RabbitConfig.QUEUE_LIFECYCLE_DLQ},
            containerFactory = "dlqListenerContainerFactory")
    public void onDeadLetter(byte[] body, @Headers Map<String, Object> headers) {
        log.error("DLQ 告警: firstDeathQueue={} firstDeathReason={} deathCount={} body={}",
                headers.get("x-first-death-queue"),
                headers.get("x-first-death-reason"),
                headers.get("x-retry-count"),
                new String(body, StandardCharsets.UTF_8));
    }
}
