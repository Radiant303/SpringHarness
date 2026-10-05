package com.spring.gateway.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.spring.gateway.entity.UsageRecord;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.util.List;
import java.util.Map;

/**
 * usage_records 表的 Mapper。
 *
 * @author hanbing
 * @since 2026-10-05
 */
@Mapper
public interface UsageRecordMapper extends BaseMapper<UsageRecord> {

    /**
     * 管理后台用量统计：按 用户 × 模型 分组的聚合（可选按用户与时间段过滤）。
     *
     * @param userId 只看该用户；null 为全部
     * @param from   起始时间（含），如 2026-10-01 或 2026-10-01 08:00:00；null 不限
     * @param to     截止时间（不含），格式同上；null 不限
     * @return 每行含 userId/username/modelName/turns/requests/inputTokens/
     *         cacheReadTokens/cacheWriteTokens/outputTokens
     */
    @Select("""
            SELECT CAST(u.id AS CHAR) AS userId, u.username AS username, r.model_name AS modelName,
                   COUNT(*) AS turns, SUM(r.requests) AS requests,
                   SUM(r.input_tokens) AS inputTokens,
                   SUM(r.cache_read_tokens) AS cacheReadTokens,
                   SUM(r.cache_write_tokens) AS cacheWriteTokens,
                   SUM(r.output_tokens) AS outputTokens
            FROM usage_records r JOIN users u ON u.id = r.user_id
            WHERE (#{userId} IS NULL OR r.user_id = #{userId})
              AND (#{from} IS NULL OR r.created_at >= #{from})
              AND (#{to} IS NULL OR r.created_at < #{to})
            GROUP BY u.id, u.username, r.model_name
            ORDER BY u.id ASC, inputTokens DESC
            """)
    List<Map<String, Object>> sumByUser(@Param("userId") Long userId,
                                        @Param("from") String from,
                                        @Param("to") String to);
}
