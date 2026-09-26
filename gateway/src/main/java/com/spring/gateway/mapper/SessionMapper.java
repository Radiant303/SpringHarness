package com.spring.gateway.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.spring.gateway.entity.Session;
import org.apache.ibatis.annotations.Mapper;

/**
 * sessions 表 Mapper。
 *
 * @author hanbing
 * @since 2026-09-26
 */
@Mapper
public interface SessionMapper extends BaseMapper<Session> {
}
