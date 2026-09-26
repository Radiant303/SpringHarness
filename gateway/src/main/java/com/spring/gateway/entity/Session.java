package com.spring.gateway.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

/**
 * sessions 表实体。
 *
 * @author hanbing
 * @since 2026-09-26
 */
@Data
@TableName("sessions")
public class Session {

    /**
     * 状态：活跃
     */
    public static final String STATUS_ACTIVE = "active";

    /**
     * 状态：已删除（软删除）
     */
    public static final String STATUS_DELETED = "deleted";

    /**
     * 主键，UUID 字符串
     */
    @TableId(type = IdType.INPUT)
    private String id;

    /**
     * 所属用户 ID
     */
    private Long userId;

    /**
     * 会话标题，取首条用户消息的截断文本
     */
    private String title;

    /**
     * 工作区目录路径
     */
    private String workspacePath;

    /**
     * 当前段号，会话历史压缩改写后自增
     */
    private Integer currentSegment;

    /**
     * 状态：active / deleted
     */
    private String status;

    /**
     * 创建时间。数据库有默认值，插入时保持 null 即可生效
     */
    private LocalDateTime createdAt;

    /**
     * 更新时间。数据库有默认值，插入时保持 null 即可生效
     */
    private LocalDateTime updatedAt;
}
