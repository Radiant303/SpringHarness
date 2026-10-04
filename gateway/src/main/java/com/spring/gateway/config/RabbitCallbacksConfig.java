package com.spring.gateway.config;

import jakarta.annotation.PostConstruct;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.context.annotation.Configuration;

/**
 * RabbitMQ 发布确认与路由失败回调的装配配置
 *
 * @author hanbing
 * @since 2026-10-02
 */
@Slf4j
@Configuration
@RequiredArgsConstructor
public class RabbitCallbacksConfig {

    private final RabbitTemplate rabbitTemplate;

    /**
     * 注册发布确认与路由失败回调
     */
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
