package com.spring.gateway.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.spring.gateway.entity.Message;
import org.apache.ibatis.annotations.Mapper;

/**
 * messages 表的 Mapper。
 *
 * @author hanbing
 * @since 2026-10-03
 */
@Mapper
public interface MessageMapper extends BaseMapper<Message> {
}
