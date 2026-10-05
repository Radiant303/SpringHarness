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

    /** 角色：站长。 */
    public static final String ROLE_OWNER = "owner";

    /** 角色：管理员。 */
    public static final String ROLE_ADMIN = "admin";

    /** 角色：普通用户。 */
    public static final String ROLE_USER = "user";

    /** 账号状态：正常。 */
    public static final String STATUS_ACTIVE = "active";

    /** 账号状态：已禁用。 */
    public static final String STATUS_DISABLED = "disabled";

    /** 用户 ID，雪花 ID。 */
    @TableId(type = IdType.INPUT)
    private Long id;

    /** 用户名，唯一。 */
    private String username;

    /** 密码哈希（BCrypt）。 */
    private String passwordHash;

    /** 存储配额（字节）：用户全部 work 目录占用合计的上限。 */
    private Long quotaBytes;

    /** 角色：owner / admin / user。 */
    private String role;

    /** 账号状态：active / disabled。 */
    private String status;

    /** 单工作区上限覆盖值（字节）；null = 跟随全局设置。 */
    private Long workQuotaBytes;

    /** 积分余额；一切变动经流水 + 事务内更新完成。 */
    private java.math.BigDecimal pointsBalance;

    /** 创建时间（UTC）。 */
    private LocalDateTime createdAt;
}
