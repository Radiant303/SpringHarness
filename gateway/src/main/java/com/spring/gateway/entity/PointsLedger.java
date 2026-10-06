package com.spring.gateway.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.math.BigDecimal;
import java.time.LocalDateTime;

/**
 * points_ledger 表的实体：积分流水（append-only）。
 *
 * <p>余额永远可由流水推出；只插不改。(type, ref_id) 唯一约束是幂等锚
 * （ref_id 为 NULL 的行不受约束，MySQL 视 NULL 互不相等）。
 *
 * @author hanbing
 * @since 2026-10-05
 */
@Data
@TableName("points_ledger")
public class PointsLedger {

    /** 类型：派发预扣。 */
    public static final String TYPE_HOLD = "HOLD";

    /** 类型：结算净差（多退少补，可正可负）。 */
    public static final String TYPE_SETTLE = "SETTLE";

    /** 类型：预扣释放退回。 */
    public static final String TYPE_RELEASE = "RELEASE";

    /** 类型：无预扣直接结算（wake 轮等绕过派发的路径）。 */
    public static final String TYPE_DIRECT = "DIRECT";

    /** 类型：站长调账。 */
    public static final String TYPE_ADJUST = "ADJUST";

    /** 类型：兑换码入账（ref_id = 码 ID）。 */
    public static final String TYPE_REDEEM = "REDEEM";

    /** 主键，雪花 ID。 */
    @TableId(type = IdType.INPUT)
    private Long id;

    /** 所属用户 ID。 */
    private Long userId;

    /** 变动额（积分，有符号；负 = 扣）。 */
    private BigDecimal changeAmount;

    /** 变动后余额（审计快照）。 */
    private BigDecimal balanceAfter;

    /** 类型：HOLD / SETTLE / RELEASE / DIRECT / ADJUST。 */
    private String type;

    /** 关联单号：turn_id；ADJUST 时为调账操作单号（雪花）。 */
    private String refId;

    /** 结算时实际计费的模型名。 */
    private String modelName;

    /** ADJUST 的操作人用户 ID。 */
    private Long operatorId;

    /** ADJUST 的事由。 */
    private String reason;

    /** 记录时间（UTC）。 */
    private LocalDateTime createdAt;
}
