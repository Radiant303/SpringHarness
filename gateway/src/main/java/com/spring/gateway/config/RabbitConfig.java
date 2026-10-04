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
 * 定义 turn 派发、取消、完成事件所用的 MQ 控制面拓扑。
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

    /** 业务队列对应的死信队列 */
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
     * 消息体统一 JSON 序列化，注入后 RabbitTemplate 自动使用
     */
    @Bean
    public MessageConverter jsonMessageConverter() {
        return new JacksonJsonMessageConverter();
    }

    /** Boot 4 不再自动装配 RabbitAdmin，显式声明 */
    @Bean
    public RabbitAdmin rabbitAdmin(ConnectionFactory connectionFactory) {
        return new RabbitAdmin(connectionFactory);
    }

    /**
     * DLQ 监听专用容器工厂：DLQ 中可能积压无法反序列化的坏消息，
     * 必须改用不会转换失败的 SimpleMessageConverter
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
