package com.spring.gateway.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.spring.gateway.entity.User;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

import java.math.BigDecimal;

/**
 * users 表的 Mapper。
 *
 * @author hanbing
 * @since 2026-09-26
 */
@Mapper
public interface UserMapper extends BaseMapper<User> {

    /**
     * 行锁读积分余额（SELECT ... FOR UPDATE）。
     *
     * <p>积分变动的第一步：同事务内后续的余额写回以此快照为基，
     * 并发的两笔积分交易在行锁上串行，杜绝丢失更新。
     *
     * @param id 用户 ID
     * @return 当前积分余额
     */
    @Select("SELECT points_balance FROM users WHERE id = #{id} FOR UPDATE")
    BigDecimal selectBalanceForUpdate(@Param("id") Long id);

    /**
     * 写回积分余额（绝对值）；只允许在 selectBalanceForUpdate 之后同事务调用。
     *
     * @param id      用户 ID
     * @param balance 新余额
     * @return 受影响行数
     */
    @Update("UPDATE users SET points_balance = #{balance} WHERE id = #{id}")
    int updateBalance(@Param("id") Long id, @Param("balance") BigDecimal balance);
}
