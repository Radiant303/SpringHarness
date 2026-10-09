package com.spring.gateway.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.spring.gateway.common.BizException;
import com.spring.gateway.dto.AdminModelDefRequest;
import com.spring.gateway.dto.AdminProviderRequest;
import com.spring.gateway.entity.ModelDefinition;
import com.spring.gateway.entity.ModelProvider;
import com.spring.gateway.entity.SystemSetting;
import com.spring.gateway.mapper.ModelDefinitionMapper;
import com.spring.gateway.mapper.ModelProviderMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.List;

/**
 * 模型配置管理：Provider 与模型定义的增删改 + 默认模型设置（均仅站长）。
 *
 * <p>配置存 model_providers / model_definitions 两张表。
 * 保护规则：被模型引用的 Provider 不可删；默认模型不可停用/删除。
 *
 * @author hanbing
 * @since 2026-10-09
 */
@Service
@RequiredArgsConstructor
public class AdminModelConfigService {

    private final ModelProviderMapper providerMapper;
    private final ModelDefinitionMapper modelMapper;
    private final SystemSettingService systemSettingService;
    private final ModelCatalogCache modelCatalogCache;

    /**
     * 全部 Provider（按名称排序）
     *
     * @return Provider 列表
     */
    public List<ModelProvider> listProviders() {
        return providerMapper.selectList(new LambdaQueryWrapper<ModelProvider>().orderByAsc(ModelProvider::getName));
    }

    /**
     * 全部模型定义（按 ID 排序）
     *
     * @return 模型列表
     */
    public List<ModelDefinition> listModels() {
        return modelMapper.selectList(new LambdaQueryWrapper<ModelDefinition>().orderByAsc(ModelDefinition::getId));
    }

    /**
     * 新建或更新 Provider（按主键 name upsert）。
     * apiKey / baseUrl 传空 = 保持不变；新建时 apiKey 必填。
     *
     * @param req Provider 请求
     * @throws BizException 类型不支持（400）；新建缺 API Key（400）
     */
    @Transactional
    public void upsertProvider(AdminProviderRequest req) {
        if (!ModelProvider.SUPPORTED_TYPES.contains(req.type())) {
            throw new BizException(400, "不支持的 Provider 类型: " + req.type()
                    + "（支持 " + String.join("/", ModelProvider.SUPPORTED_TYPES) + "）");
        }
        ModelProvider row = providerMapper.selectById(req.name());
        String apiKey = req.apiKey() == null ? "" : req.apiKey().trim();
        String baseUrl = req.baseUrl() == null ? "" : req.baseUrl().trim();
        if (row == null) {
            if (apiKey.isEmpty()) {
                throw new BizException(400, "新建 Provider 必须填写 API Key");
            }
            row = new ModelProvider();
            row.setName(req.name());
            row.setType(req.type());
            row.setApiKey(apiKey);
            row.setBaseUrl(baseUrl.isEmpty() ? null : baseUrl);
            row.setUpdatedAt(LocalDateTime.now(ZoneOffset.UTC));
            providerMapper.insert(row);
            modelCatalogCache.invalidate();
            return;
        }
        row.setType(req.type());
        if (!apiKey.isEmpty()) {
            row.setApiKey(apiKey);
        }
        if (!baseUrl.isEmpty()) {
            row.setBaseUrl(baseUrl);
        }
        row.setUpdatedAt(LocalDateTime.now(ZoneOffset.UTC));
        providerMapper.updateById(row);
        modelCatalogCache.invalidate();
    }

    /**
     * 删除 Provider；仍有模型引用时拒绝
     *
     * @param name Provider 名
     * @throws BizException 不存在（404）；被引用（409）
     */
    @Transactional
    public void deleteProvider(String name) {
        if (providerMapper.selectById(name) == null) {
            throw new BizException(404, "Provider 不存在");
        }
        long refs = modelMapper.selectCount(
                new LambdaQueryWrapper<ModelDefinition>().eq(ModelDefinition::getProvider, name));
        if (refs > 0) {
            throw new BizException(409, "仍有 " + refs + " 个模型引用该 Provider，请先删除对应模型");
        }
        providerMapper.deleteById(name);
        modelCatalogCache.invalidate();
    }

    /**
     * 新建或更新模型定义（按主键 id upsert）。
     * id 必须以 "provider/" 开头；停用默认模型会被拒绝。
     *
     * @param req 模型请求
     * @throws BizException Provider 不存在（400）；id 与 provider 不匹配（400）；停用默认模型（409）
     */
    @Transactional
    public void upsertModel(AdminModelDefRequest req) {
        if (providerMapper.selectById(req.provider()) == null) {
            throw new BizException(400, "Provider 不存在: " + req.provider());
        }
        if (!req.id().startsWith(req.provider() + "/")) {
            throw new BizException(400, "模型 ID 必须以 \"" + req.provider() + "/\" 开头");
        }
        if (systemSettingService.getDefaultModel().equals(req.id()) && !req.enabled()) {
            throw new BizException(409, "默认模型不可停用，请先切换默认模型");
        }
        ModelDefinition row = modelMapper.selectById(req.id());
        boolean isNew = row == null;
        if (isNew) {
            row = new ModelDefinition();
            row.setId(req.id());
            row.setCreatedAt(LocalDateTime.now(ZoneOffset.UTC));
        }
        row.setProvider(req.provider());
        row.setModel(req.model());
        row.setDisplayName(req.displayName());
        row.setMaxContextSize(req.maxContextSize());
        row.setMaxOutputSize(req.maxOutputSize());
        row.setCapabilities(joinCsv(req.capabilities()));
        row.setSupportEfforts(joinCsv(req.supportEfforts()));
        row.setDefaultEffort(req.defaultEffort() == null ? "" : req.defaultEffort().trim());
        String reasoningKey = req.reasoningKey() == null ? "" : req.reasoningKey().trim();
        row.setReasoningKey(reasoningKey.isEmpty() ? null : reasoningKey);
        row.setEnabled(req.enabled());
        row.setUpdatedAt(LocalDateTime.now(ZoneOffset.UTC));
        if (isNew) {
            modelMapper.insert(row);
        } else {
            modelMapper.updateById(row);
        }
        modelCatalogCache.invalidate();
    }

    /**
     * 删除模型定义；默认模型不可删
     *
     * @param id 模型 ID
     * @throws BizException 不存在（404）；是默认模型（409）
     */
    @Transactional
    public void deleteModel(String id) {
        if (modelMapper.selectById(id) == null) {
            throw new BizException(404, "模型不存在");
        }
        if (systemSettingService.getDefaultModel().equals(id)) {
            throw new BizException(409, "默认模型不可删除，请先切换默认模型");
        }
        modelMapper.deleteById(id);
        modelCatalogCache.invalidate();
    }

    /**
     * 设置默认模型；目标必须存在且已启用
     *
     * @param modelId 模型 ID
     * @throws BizException 模型不存在或未启用（400）
     */
    public void setDefaultModel(String modelId) {
        ModelDefinition row = modelMapper.selectById(modelId);
        if (row == null || !Boolean.TRUE.equals(row.getEnabled())) {
            throw new BizException(400, "模型不存在或未启用: " + modelId);
        }
        systemSettingService.set(SystemSetting.KEY_DEFAULT_MODEL, modelId);
        modelCatalogCache.invalidate();
    }

    /** List → CSV（null 当空列表；元素去空白、去空项）。 */
    private static String joinCsv(List<String> items) {
        if (items == null) {
            return "";
        }
        return items.stream()
                .map(String::trim)
                .filter(s -> !s.isEmpty())
                .reduce((a, b) -> a + "," + b)
                .orElse("");
    }
}
