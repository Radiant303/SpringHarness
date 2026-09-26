package com.spring.gateway.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

/**
 * users 表实体。
 *
 * @author hanbing
 * @since 2026-09-26
 */
@Data
@TableName("users")
public class User {

    /**
     * 主键，由雪花 ID 生成器显式赋值（IdType.INPUT），不使用数据库自增
     */
    @TableId(type = IdType.INPUT)
    private Long id;

    /**
     * 用户名，唯一
     */
    private String username;

    /**
     * BCrypt 密码哈希
     */
    private String passwordHash;

    /**
     * 存储配额，单位字节。数据库有默认值（server default），插入时保持 null 即可生效
     */
    private Long quotaBytes;

    /**
     * 创建时间。数据库有默认值，插入时保持 null 即可生效
     */
    private LocalDateTime createdAt;
}
