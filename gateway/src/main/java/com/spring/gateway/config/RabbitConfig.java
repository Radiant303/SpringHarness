package com.spring.gateway.config;

import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.amqp.support.converter.JacksonJsonMessageConverter;
import org.springframework.amqp.support.converter.MessageConverter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * MQ 控制面拓扑：turn 派发/取消/完成事件。
 *
 * <p>exchange 与队列全部声明为 durable，消费端（Python 引擎）侧使用 manual ack；
 * 消息体统一 JSON，turnId 为雪花 ID，消费端按 turnId 幂等。
 *
 * @author hanbing
 * @since 2026-10-02
 */
@Configuration
public class RabbitConfig {

    /** 控制面交换机（direct，durable） */
    public static final String TURN_EXCHANGE = "harness.turn";

    /** turn 派发队列：Python 引擎消费 */
    public static final String QUEUE_DISPATCH = "turn.dispatch";
    /** turn 取消队列：Python 引擎消费 */
    public static final String QUEUE_CANCEL = "turn.cancel";
    /** turn 生命周期队列：网关消费（完成/失败事件回传） */
    public static final String QUEUE_LIFECYCLE = "turn.lifecycle";

    @Bean
    public DirectExchange turnExchange() {
        return new DirectExchange(TURN_EXCHANGE, true, false);
    }

    @Bean
    public Queue dispatchQueue() {
        return QueueBuilder.durable(QUEUE_DISPATCH).build();
    }

    @Bean
    public Queue cancelQueue() {
        return QueueBuilder.durable(QUEUE_CANCEL).build();
    }

    @Bean
    public Queue lifecycleQueue() {
        return QueueBuilder.durable(QUEUE_LIFECYCLE).build();
    }

    @Bean
    public Binding dispatchBinding(DirectExchange turnExchange, Queue dispatchQueue) {
        return BindingBuilder.bind(dispatchQueue).to(turnExchange).with(QUEUE_DISPATCH);
    }

    @Bean
    public Binding cancelBinding(DirectExchange turnExchange, Queue cancelQueue) {
        return BindingBuilder.bind(cancelQueue).to(turnExchange).with(QUEUE_CANCEL);
    }

    @Bean
    public Binding lifecycleBinding(DirectExchange turnExchange, Queue lifecycleQueue) {
        return BindingBuilder.bind(lifecycleQueue).to(turnExchange).with(QUEUE_LIFECYCLE);
    }

    /**
     * 消息体统一 JSON 序列化（Jackson 3，与网关其他模块一致），
     * 注入后 RabbitTemplate 会自动使用
     */
    @Bean
    public MessageConverter jsonMessageConverter() {
        return new JacksonJsonMessageConverter();
    }
}
