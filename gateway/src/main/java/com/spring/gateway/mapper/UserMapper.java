package com.spring.gateway.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.spring.gateway.entity.User;
import org.apache.ibatis.annotations.Mapper;

/**
 * users 表的 Mapper。
 *
 * @author hanbing
 * @since 2026-09-26
 */
@Mapper
public interface UserMapper extends BaseMapper<User> {
}
