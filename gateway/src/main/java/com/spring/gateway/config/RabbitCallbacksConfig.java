package com.spring.gateway.config;

import jakarta.annotation.PostConstruct;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.context.annotation.Configuration;

/**
 * publisher confirm / returns 回调装配：broker 显式拒收或路由失败时留下错误日志。
 * 逐条同步确认（含失败回退）在 TurnDispatchService 的 invoke 里做，这里兜住异步漏网的。
 *
 * @author hanbing
 * @since 2026-10-02
 */
@Slf4j
@Configuration
@RequiredArgsConstructor
public class RabbitCallbacksConfig {

    private final RabbitTemplate rabbitTemplate;

    @PostConstruct
    void registerCallbacks() {
        rabbitTemplate.setConfirmCallback((correlationData, ack, cause) -> {
            if (!ack) {
                log.error("MQ 发布被 broker 拒收: cause={} correlation={}", cause, correlationData);
            }
        });
        rabbitTemplate.setReturnsCallback(returned ->
                log.error("MQ 消息路由失败: exchange={} routingKey={} reply={}",
                        returned.getExchange(), returned.getRoutingKey(), returned.getReplyText()));
    }
}
