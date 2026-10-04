package com.spring.gateway.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.spring.gateway.entity.Work;
import org.apache.ibatis.annotations.Mapper;

/**
 * works 表的 Mapper。
 *
 * @author hanbing
 * @since 2026-10-04
 */
@Mapper
public interface WorkMapper extends BaseMapper<Work> {
}
