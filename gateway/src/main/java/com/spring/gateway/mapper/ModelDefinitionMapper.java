package com.spring.gateway.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.spring.gateway.entity.ModelDefinition;
import org.apache.ibatis.annotations.Mapper;

/**
 * model_definitions 表的 Mapper。
 *
 * @author hanbing
 * @since 2026-10-09
 */
@Mapper
public interface ModelDefinitionMapper extends BaseMapper<ModelDefinition> {
}
