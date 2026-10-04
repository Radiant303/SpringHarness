package com.spring.gateway.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

/**
 * messages 表实体：一条消息就是 Python 侧单条 ModelMessage dump 后的 JSON。
 *
 * @author hanbing
 * @since 2026-10-03
 */
@Data
@TableName("messages")
public class Message {

    /**
     * 主键，数据库自增
     */
    @TableId(type = IdType.AUTO)
    private Long id;

    /**
     * 所属会话 ID
     */
    private String sessionId;

    /**
     * 段号：会话历史压缩改写（current_segment 自增）后，消息整体写入新段
     */
    private Integer segmentNo;

    /**
     * payload：messages.payload JSON 列原文，Java 不解析其内容，读出后原样返回
     */
    private String payload;

    /**
     * 创建时间。数据库有默认值，插入时保持 null 即可生效
     */
    private LocalDateTime createdAt;
}
