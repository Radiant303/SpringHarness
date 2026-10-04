package com.spring.gateway.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

/**
 * sessions 表的实体。
 *
 * @author hanbing
 * @since 2026-09-26
 */
@Data
@TableName("sessions")
public class Session {

    /** 会话状态：活跃。 */
    public static final String STATUS_ACTIVE = "active";

    /** 会话状态：已删除。 */
    public static final String STATUS_DELETED = "deleted";

    /** 会话 ID，UUID。 */
    @TableId(type = IdType.INPUT)
    private String id;

    /** 所属用户 ID。 */
    private Long userId;

    /** 所属 work ID，同 work 的会话共享同一工作区目录。 */
    private String workId;

    /** 会话标题。 */
    private String title;

    /** 当前历史段号。 */
    private Integer currentSegment;

    /** 会话状态。 */
    private String status;

    /** 创建时间。 */
    private LocalDateTime createdAt;

    /** 更新时间。 */
    private LocalDateTime updatedAt;
}
