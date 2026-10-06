package com.spring.gateway.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.spring.gateway.entity.RedeemCode;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Update;

/**
 * redeem_codes 表的 Mapper。
 *
 * @author hanbing
 * @since 2026-10-06
 */
@Mapper
public interface RedeemCodeMapper extends BaseMapper<RedeemCode> {

    /**
     * 兑换抢占：ACTIVE 且未过期的码原子地转为 REDEEMED，并置兑换人/兑换时间/软删除。
     *
     * <p>影响行数 = 1 表示当前调用是唯一的赢家；并发的重复兑换、双击、
     * 重放全部因条件不满足返回 0，无需分布式锁。过期判定在 SQL 内完成，
     * 正确性不依赖任何扫描器时效。
     *
     * @param code   规范形兑换码（大写、无连字符）
     * @param userId 兑换人用户 ID
     * @return 受影响行数（1 = 抢占成功）
     */
    @Update("UPDATE redeem_codes SET status = 'REDEEMED', redeemed_by = #{userId},"
            + " redeemed_at = NOW(6), deleted_at = NOW(6)"
            + " WHERE code = #{code} AND status = 'ACTIVE'"
            + " AND (expires_at IS NULL OR expires_at > NOW(6))")
    int claim(@Param("code") String code, @Param("userId") Long userId);

    /**
     * 作废：仅 ACTIVE 的码可作废（已兑换/已作废不受影响）。
     *
     * @param id 码 ID
     * @return 受影响行数（1 = 作废成功）
     */
    @Update("UPDATE redeem_codes SET status = 'REVOKED' WHERE id = #{id} AND status = 'ACTIVE'")
    int revoke(@Param("id") Long id);
}
