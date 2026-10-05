package com.spring.gateway.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.spring.gateway.entity.SystemSetting;
import org.apache.ibatis.annotations.Mapper;

/**
 * system_settings 表的 Mapper。
 *
 * @author hanbing
 * @since 2026-10-05
 */
@Mapper
public interface SystemSettingMapper extends BaseMapper<SystemSetting> {
}
