package com.spring.gateway.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.spring.gateway.entity.PointsHold;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Update;

/**
 * points_holds 表的 Mapper。
 *
 * @author hanbing
 * @since 2026-10-05
 */
@Mapper
public interface PointsHoldMapper extends BaseMapper<PointsHold> {

    /**
     * 预扣收口的条件状态迁移：HELD → 目标状态。
     *
     * <p>结算与释放（含过期扫描）可能并发撞同一笔预扣，带 status='HELD' 条件的
     * UPDATE 保证只有一个赢家（返回 1），输家返回 0 后必须放弃退款/扣款动作。
     *
     * @param turnId 预扣单号
     * @param to     目标状态（SETTLED / RELEASED）
     * @return 受影响行数：1 = 本次调用赢得收口权，0 = 已被其他路径收口或单号不存在
     */
    @Update("UPDATE points_holds SET status = #{to}, settled_at = UTC_TIMESTAMP(6)"
            + " WHERE turn_id = #{turnId} AND status = 'HELD'")
    int transition(@Param("turnId") String turnId, @Param("to") String to);
}
