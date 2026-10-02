package com.spring.gateway.config;

import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.amqp.rabbit.config.SimpleRabbitListenerContainerFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.core.RabbitAdmin;
import org.springframework.amqp.support.converter.JacksonJsonMessageConverter;
import org.springframework.amqp.support.converter.MessageConverter;
import org.springframework.amqp.support.converter.SimpleMessageConverter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * MQ 控制面拓扑：turn 派发/取消/完成事件。
 *
 * <p>exchange 与队列全部 durable，消费端 manual ack；消息体统一 JSON，
 * turnId 为雪花 ID，消费端按 turnId 幂等。
 *
 * <p>可靠性（加固）：每个业务队列挂死信交换机 harness.turn.dlx，被拒
 * （nack 不 requeue）的消息进同名 .dlq 队列，由 DlqListener 告警而不是静默丢失。
 *
 * <p>注意：Python 侧（cloud/mq.py）声明的同名队列参数必须与这里完全一致，
 * 否则 RabbitMQ 报 406 PRECONDITION_FAILED。
 *
 * @author hanbing
 * @since 2026-10-02
 */
@Configuration
public class RabbitConfig {

    /** 控制面交换机（direct，durable） */
    public static final String TURN_EXCHANGE = "harness.turn";
    /** 死信交换机：三个业务队列共用一个，按原队列名路由 */
    public static final String TURN_DLX = "harness.turn.dlx";

    /** turn 派发队列：Python 引擎消费 */
    public static final String QUEUE_DISPATCH = "turn.dispatch";
    /** turn 取消队列：Python 引擎消费 */
    public static final String QUEUE_CANCEL = "turn.cancel";
    /** turn 生命周期队列：网关消费（完成/失败事件回传） */
    public static final String QUEUE_LIFECYCLE = "turn.lifecycle";

    public static final String QUEUE_DISPATCH_DLQ = QUEUE_DISPATCH + ".dlq";
    public static final String QUEUE_CANCEL_DLQ = QUEUE_CANCEL + ".dlq";
    public static final String QUEUE_LIFECYCLE_DLQ = QUEUE_LIFECYCLE + ".dlq";

    @Bean
    public DirectExchange turnExchange() {
        return new DirectExchange(TURN_EXCHANGE, true, false);
    }

    @Bean
    public DirectExchange turnDeadLetterExchange() {
        return new DirectExchange(TURN_DLX, true, false);
    }

    /** 业务队列统一挂死信：被拒（nack 不 requeue）或 TTL 过期的消息转入 DLQ */
    private static Queue businessQueue(String name) {
        return QueueBuilder.durable(name)
                .withArgument("x-dead-letter-exchange", TURN_DLX)
                .withArgument("x-dead-letter-routing-key", name + ".dlq")
                .build();
    }

    @Bean
    public Queue dispatchQueue() {
        return businessQueue(QUEUE_DISPATCH);
    }

    @Bean
    public Queue cancelQueue() {
        return businessQueue(QUEUE_CANCEL);
    }

    @Bean
    public Queue lifecycleQueue() {
        return businessQueue(QUEUE_LIFECYCLE);
    }

    @Bean
    public Queue dispatchDlq() {
        return QueueBuilder.durable(QUEUE_DISPATCH_DLQ).build();
    }

    @Bean
    public Queue cancelDlq() {
        return QueueBuilder.durable(QUEUE_CANCEL_DLQ).build();
    }

    @Bean
    public Queue lifecycleDlq() {
        return QueueBuilder.durable(QUEUE_LIFECYCLE_DLQ).build();
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

    @Bean
    public Binding dispatchDlqBinding(DirectExchange turnDeadLetterExchange, Queue dispatchDlq) {
        return BindingBuilder.bind(dispatchDlq).to(turnDeadLetterExchange).with(QUEUE_DISPATCH_DLQ);
    }

    @Bean
    public Binding cancelDlqBinding(DirectExchange turnDeadLetterExchange, Queue cancelDlq) {
        return BindingBuilder.bind(cancelDlq).to(turnDeadLetterExchange).with(QUEUE_CANCEL_DLQ);
    }

    @Bean
    public Binding lifecycleDlqBinding(DirectExchange turnDeadLetterExchange, Queue lifecycleDlq) {
        return BindingBuilder.bind(lifecycleDlq).to(turnDeadLetterExchange).with(QUEUE_LIFECYCLE_DLQ);
    }

    /**
     * 消息体统一 JSON 序列化（Jackson 3，与网关其他模块一致），
     * 注入后 RabbitTemplate 会自动使用
     */
    @Bean
    public MessageConverter jsonMessageConverter() {
        return new JacksonJsonMessageConverter();
    }

    /** Boot 4 不再自动装配 RabbitAdmin，显式声明供 MqMonitor 读队列深度 */
    @Bean
    public RabbitAdmin rabbitAdmin(ConnectionFactory connectionFactory) {
        return new RabbitAdmin(connectionFactory);
    }

    /**
     * DLQ 监听专用容器工厂：SimpleMessageConverter 对任何消息体都不会转换失败
     * （非文本 contentType 原样给 byte[]）。DLQ 收的就是毒死消费端的坏消息，
     * 默认工厂的 Jackson 转换器会在告警逻辑执行前先抛异常，必须换掉。
     */
    @Bean
    public SimpleRabbitListenerContainerFactory dlqListenerContainerFactory(
            ConnectionFactory connectionFactory) {
        SimpleRabbitListenerContainerFactory factory = new SimpleRabbitListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setMessageConverter(new SimpleMessageConverter());
        return factory;
    }
}
