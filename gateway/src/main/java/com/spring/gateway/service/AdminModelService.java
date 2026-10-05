package com.spring.gateway.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.spring.gateway.common.BizException;
import com.spring.gateway.common.SnowflakeIdGenerator;
import com.spring.gateway.dto.AdminModelRequest;
import com.spring.gateway.entity.ModelRate;
import com.spring.gateway.mapper.ModelRateMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.List;

/**
 * 模型资费卡管理：增删改仅站长（controller 层校验），查看对 owner/admin 开放。
 *
 * <p>兜底卡（model_name = "default"）受保护：不可删除、不可改名、不可停用——
 * 它是预扣估算与未知模型结算的最后依据。
 *
 * @author hanbing
 * @since 2026-10-05
 */
@Service
@RequiredArgsConstructor
public class AdminModelService {

    private final ModelRateMapper modelRateMapper;
    private final SnowflakeIdGenerator idGenerator;

    /**
     * 全部资费卡，default 行置顶，其余按模型名排序
     *
     * @return 资费卡列表
     */
    public List<ModelRate> list() {
        List<ModelRate> rows = modelRateMapper.selectList(new LambdaQueryWrapper<ModelRate>()
                .orderByAsc(ModelRate::getModelName));
        rows.sort((a, b) -> Boolean.compare(
                !ModelRate.DEFAULT_MODEL_NAME.equals(a.getModelName()),
                !ModelRate.DEFAULT_MODEL_NAME.equals(b.getModelName())));
        return rows;
    }

    /**
     * 新建资费卡
     *
     * @param req 模型名与四项费率
     * @return 新建行
     * @throws BizException 模型名已存在（409）
     */
    public ModelRate create(AdminModelRequest req) {
        LocalDateTime now = LocalDateTime.now(ZoneOffset.UTC);
        ModelRate row = new ModelRate();
        row.setId(idGenerator.nextId());
        apply(row, req);
        row.setCreatedAt(now);
        row.setUpdatedAt(now);
        try {
            modelRateMapper.insert(row);
        } catch (DuplicateKeyException e) {
            throw new BizException(409, "模型名已存在: " + req.modelName());
        }
        return row;
    }

    /**
     * 修改资费卡；兜底卡不可改名、不可停用
     *
     * @param id  资费卡 ID
     * @param req 新值
     * @throws BizException 不存在（404）；触碰兜底卡保护（403）；模型名撞车（409）
     */
    public void update(Long id, AdminModelRequest req) {
        ModelRate row = requireRow(id);
        if (ModelRate.DEFAULT_MODEL_NAME.equals(row.getModelName())
                && !ModelRate.DEFAULT_MODEL_NAME.equals(req.modelName())) {
            throw new BizException(403, "兜底资费卡（default）不可改名");
        }
        if (ModelRate.DEFAULT_MODEL_NAME.equals(row.getModelName()) && Boolean.FALSE.equals(req.enabled())) {
            throw new BizException(403, "兜底资费卡（default）不可停用");
        }
        apply(row, req);
        row.setUpdatedAt(LocalDateTime.now(ZoneOffset.UTC));
        try {
            modelRateMapper.updateById(row);
        } catch (DuplicateKeyException e) {
            throw new BizException(409, "模型名已存在: " + req.modelName());
        }
    }

    /**
     * 删除资费卡；兜底卡不可删除
     *
     * @param id 资费卡 ID
     * @throws BizException 不存在（404）；兜底卡（403）
     */
    public void delete(Long id) {
        ModelRate row = requireRow(id);
        if (ModelRate.DEFAULT_MODEL_NAME.equals(row.getModelName())) {
            throw new BizException(403, "兜底资费卡（default）不可删除");
        }
        modelRateMapper.deleteById(id);
    }

    private ModelRate requireRow(Long id) {
        ModelRate row = modelRateMapper.selectById(id);
        if (row == null) {
            throw new BizException(404, "资费卡不存在");
        }
        return row;
    }

    private static void apply(ModelRate row, AdminModelRequest req) {
        row.setModelName(req.modelName().trim());
        row.setInputPoints(req.inputPoints());
        row.setCacheReadPoints(req.cacheReadPoints());
        row.setCacheWritePoints(req.cacheWritePoints());
        row.setOutputPoints(req.outputPoints());
        row.setEnabled(req.enabled() == null || req.enabled());
    }
}
