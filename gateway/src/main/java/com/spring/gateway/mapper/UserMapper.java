package com.spring.gateway.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.spring.gateway.entity.User;
import org.apache.ibatis.annotations.Mapper;

/**
 * users 表 Mapper。继承 BaseMapper 获得单表 CRUD 能力。
 *
 * @author hanbing
 * @since 2026-09-26
 */
@Mapper
public interface UserMapper extends BaseMapper<User> {
}
