package com.spring.gateway.controller;

import com.spring.gateway.common.AuthInterceptor;
import com.spring.gateway.common.BizException;
import com.spring.gateway.common.Result;
import com.spring.gateway.common.TimeFormat;
import com.spring.gateway.dto.AdminDefaultModelRequest;
import com.spring.gateway.dto.AdminModelDefRequest;
import com.spring.gateway.dto.AdminModelDefView;
import com.spring.gateway.dto.AdminModelIdRequest;
import com.spring.gateway.dto.AdminProviderRequest;
import com.spring.gateway.dto.AdminProviderView;
import com.spring.gateway.entity.ModelDefinition;
import com.spring.gateway.entity.ModelProvider;
import com.spring.gateway.entity.User;
import com.spring.gateway.service.AdminModelConfigService;
import com.spring.gateway.service.SystemSettingService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Arrays;
import java.util.List;
import java.util.Map;

/**
 * 模型配置管理接口（Provider / 模型定义 / 默认模型）：查看对 owner/admin 开放，修改仅站长。
 *
 * @author hanbing
 * @since 2026-10-09
 */
@RestController
@RequestMapping("/api/admin/model-config")
@RequiredArgsConstructor
public class AdminModelConfigController {

    private final AdminModelConfigService modelConfigService;
    private final SystemSettingService systemSettingService;

    /**
     * 模型配置快照：providers（不含 api_key）+ models + defaultModel
     *
     * @return 配置快照
     */
    @GetMapping
    public Result<Map<String, Object>> get() {
        String defaultModel = systemSettingService.getDefaultModel();
        return Result.ok(Map.of(
                "providers", modelConfigService.listProviders().stream()
                        .map(AdminModelConfigController::toProviderView).toList(),
                "models", modelConfigService.listModels().stream()
                        .map(m -> toModelView(m, defaultModel)).toList(),
                "defaultModel", defaultModel));
    }

    /**
     * 新建或更新 Provider（仅站长）；apiKey/baseUrl 留空 = 保持不变
     *
     * @param actorRole 当前用户角色（拦截器注入）
     * @param req       Provider 请求
     * @return 空数据返回体
     */
    @PostMapping("/providers")
    public Result<Void> upsertProvider(@RequestAttribute(AuthInterceptor.ATTR_USER_ROLE) String actorRole,
                                       @Valid @RequestBody AdminProviderRequest req) {
        requireOwner(actorRole);
        modelConfigService.upsertProvider(req);
        return Result.ok(null);
    }

    /**
     * 删除 Provider（仅站长）；被模型引用时拒绝
     *
     * @param actorRole 当前用户角色（拦截器注入）
     * @param name      Provider 名
     * @return 空数据返回体
     */
    @PostMapping("/providers/{name}/delete")
    public Result<Void> deleteProvider(@RequestAttribute(AuthInterceptor.ATTR_USER_ROLE) String actorRole,
                                       @PathVariable String name) {
        requireOwner(actorRole);
        modelConfigService.deleteProvider(name);
        return Result.ok(null);
    }

    /**
     * 新建或更新模型定义（仅站长）
     *
     * @param actorRole 当前用户角色（拦截器注入）
     * @param req       模型请求
     * @return 空数据返回体
     */
    @PostMapping("/models")
    public Result<Void> upsertModel(@RequestAttribute(AuthInterceptor.ATTR_USER_ROLE) String actorRole,
                                    @Valid @RequestBody AdminModelDefRequest req) {
        requireOwner(actorRole);
        modelConfigService.upsertModel(req);
        return Result.ok(null);
    }

    /**
     * 删除模型定义（仅站长）；默认模型不可删。
     * id 含斜杠（provider/模型名），放请求体而不是路径变量（%2F 会被按路径分隔符处理）。
     *
     * @param actorRole 当前用户角色（拦截器注入）
     * @param req       模型 ID
     * @return 空数据返回体
     */
    @PostMapping("/models/delete")
    public Result<Void> deleteModel(@RequestAttribute(AuthInterceptor.ATTR_USER_ROLE) String actorRole,
                                    @Valid @RequestBody AdminModelIdRequest req) {
        requireOwner(actorRole);
        modelConfigService.deleteModel(req.modelId());
        return Result.ok(null);
    }

    /**
     * 设置默认模型（仅站长）
     *
     * @param actorRole 当前用户角色（拦截器注入）
     * @param req       模型 ID
     * @return 空数据返回体
     */
    @PostMapping("/default")
    public Result<Void> setDefault(@RequestAttribute(AuthInterceptor.ATTR_USER_ROLE) String actorRole,
                                   @Valid @RequestBody AdminDefaultModelRequest req) {
        requireOwner(actorRole);
        modelConfigService.setDefaultModel(req.modelId());
        return Result.ok(null);
    }

    private static void requireOwner(String actorRole) {
        if (!User.ROLE_OWNER.equals(actorRole)) {
            throw new BizException(403, "仅站长可管理模型配置");
        }
    }

    private static AdminProviderView toProviderView(ModelProvider row) {
        return new AdminProviderView(
                row.getName(),
                row.getType(),
                row.getBaseUrl(),
                row.getApiKey() != null && !row.getApiKey().isBlank(),
                TimeFormat.isoUtc(row.getUpdatedAt()));
    }

    private static AdminModelDefView toModelView(ModelDefinition row, String defaultModel) {
        return new AdminModelDefView(
                row.getId(),
                row.getProvider(),
                row.getModel(),
                row.getDisplayName(),
                row.getMaxContextSize(),
                row.getMaxOutputSize(),
                splitCsv(row.getCapabilities()),
                splitCsv(row.getSupportEfforts()),
                row.getDefaultEffort(),
                row.getReasoningKey(),
                row.getEnabled(),
                row.getId().equals(defaultModel),
                TimeFormat.isoUtc(row.getUpdatedAt()));
    }

    private static List<String> splitCsv(String csv) {
        if (csv == null || csv.isBlank()) {
            return List.of();
        }
        return Arrays.stream(csv.split(",")).map(String::trim).filter(s -> !s.isEmpty()).toList();
    }
}
