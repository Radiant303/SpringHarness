package com.spring.gateway.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

/**
 * messages 表的实体。
 *
 * @author hanbing
 * @since 2026-10-03
 */
@Data
@TableName("messages")
public class Message {

    /** 主键，数据库自增。 */
    @TableId(type = IdType.AUTO)
    private Long id;

    /** 所属会话 ID。 */
    private String sessionId;

    /** 消息所属的历史段号。 */
    private Integer segmentNo;

    /** 消息内容，JSON 原文。 */
    private String payload;

    /** 创建时间。 */
    private LocalDateTime createdAt;
}
