package com.spring.gateway.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.spring.gateway.entity.UsageRecord;
import org.apache.ibatis.annotations.Mapper;

/**
 * usage_records 表的 Mapper。
 *
 * @author hanbing
 * @since 2026-10-05
 */
@Mapper
public interface UsageRecordMapper extends BaseMapper<UsageRecord> {
}
