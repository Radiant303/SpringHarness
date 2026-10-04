package com.spring.gateway.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

/**
 * users 表的实体。
 *
 * @author hanbing
 * @since 2026-09-26
 */
@Data
@TableName("users")
public class User {

    /** 用户 ID，雪花 ID。 */
    @TableId(type = IdType.INPUT)
    private Long id;

    /** 用户名，唯一。 */
    private String username;

    /** 密码的 BCrypt 哈希。 */
    private String passwordHash;

    /** 存储配额，单位字节。 */
    private Long quotaBytes;

    /** 创建时间。 */
    private LocalDateTime createdAt;
}
