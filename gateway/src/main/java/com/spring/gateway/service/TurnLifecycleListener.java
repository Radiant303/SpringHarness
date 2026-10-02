package com.spring.gateway.service;

import com.spring.gateway.config.RabbitConfig;
import lombok.extern.slf4j.Slf4j;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

import java.util.Map;

/**
 * turn 生命周期事件监听（阶段④控制面）：Python 引擎在轮次结束时回传
 * finished / cancelled / error，网关侧当前仅记录日志（后续可用于埋点、配额计量）。
 *
 * @author hanbing
 * @since 2026-10-02
 */
@Slf4j
@Component
public class TurnLifecycleListener {

    @RabbitListener(queues = RabbitConfig.QUEUE_LIFECYCLE)
    public void onTurnLifecycle(Map<String, Object> payload) {
        log.info("turn 生命周期事件: {}", payload);
    }
}
