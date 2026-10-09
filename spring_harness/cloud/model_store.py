"""云端模型目录：MySQL 为权威数据（站长在网关后台维护），Redis 做缓存。

缓存策略：Cache-Aside + 网关写后延迟双删。
- 读：先查 Redis 快照（`modelconf:catalog`，TTL 60s 兜底），未命中回源 MySQL 并回填；
  Redis 抖动时直接回源（fail-open，缓存只是提速，DB 才是真相）。
- 写：管理侧改库后删缓存，~1s 后再删一次（覆盖
  "读旧库 → 回填缓存"的并发窗口），由本模块的 TTL 兜住一切遗漏。
"""

from __future__ import annotations

import json
from typing import Any

import redis
from sqlalchemy import select

from spring_harness.cloud.db import (
    ModelDefinitionRow,
    ModelProviderRow,
    SystemSettingRow,
    get_sessionmaker,
)
from spring_harness.core.config.settings import Model as ModelConfig
from spring_harness.core.config.settings import Provider as ProviderConfig
from spring_harness.core.log import logger

# system_settings 里默认模型的键
KEY_DEFAULT_MODEL = "default_model"

# 缓存 key 与 TTL：TTL 是最终一致性兜底（延迟双删失败/遗漏时最多脏 60s）
CACHE_KEY = "modelconf:catalog"
CACHE_TTL_SECONDS = 60


def _split_csv(csv: str | None) -> list[str]:
    if not csv:
        return []
    return [item.strip() for item in csv.split(",") if item.strip()]


def _model_config_from_dict(d: dict[str, Any]) -> ModelConfig:
    return ModelConfig(
        provider=d["provider"],
        model=d["model"],
        max_context_size=d["max_context_size"],
        display_name=d["display_name"],
        max_output_size=d["max_output_size"],
        capabilities=_split_csv(d["capabilities"]),
        support_efforts=_split_csv(d["support_efforts"]),
        default_effort=d["default_effort"],
        reasoning_key=d["reasoning_key"],
    )


class DbCatalog:
    """模型配置目录的 DB 实现（满足 core.config.model.ModelCatalog 协议），带 Redis 快照缓存。"""

    def __init__(self, cache: redis.Redis | None = None) -> None:
        # cache 为 None 时退化为纯直读（测试/Redis 未装配场景）
        self._cache = cache

    def default_model(self) -> str:
        return self._snapshot()["default_model"]

    def get_model_config(self, model_id: str) -> ModelConfig | None:
        entry = self._snapshot()["models"].get(model_id)
        return _model_config_from_dict(entry) if entry is not None else None

    def get_provider_config(self, provider_name: str) -> ProviderConfig | None:
        entry = self._snapshot()["providers"].get(provider_name)
        if entry is None:
            return None
        return ProviderConfig(
            type=entry["type"], api_key=entry["api_key"], base_url=entry["base_url"],
        )

    def list_model_configs(self) -> list[tuple[str, ModelConfig]]:
        models = self._snapshot()["models"]
        return [
            (mid, _model_config_from_dict(entry))
            for mid, entry in sorted(models.items())
            if entry["enabled"]
        ]

    # ---- 快照：Redis 优先，未命中回源 MySQL 并回填 ----

    def _snapshot(self) -> dict[str, Any]:
        if self._cache is not None:
            try:
                raw = self._cache.get(CACHE_KEY)
                if raw is not None:
                    return json.loads(raw)
            except redis.RedisError as e:
                logger.warning("模型目录缓存读取失败，回源 MySQL: {}", e)
        snapshot = self._load_from_db()
        if self._cache is not None:
            try:
                self._cache.set(CACHE_KEY, json.dumps(snapshot), ex=CACHE_TTL_SECONDS)
            except redis.RedisError as e:
                logger.warning("模型目录缓存回填失败（不影响本次读取）: {}", e)
        return snapshot

    def _load_from_db(self) -> dict[str, Any]:
        with get_sessionmaker()() as s:
            providers = {
                row.name: {"type": row.type, "api_key": row.api_key, "base_url": row.base_url}
                for row in s.scalars(select(ModelProviderRow)).all()
            }
            models = {
                row.id: {
                    "provider": row.provider,
                    "model": row.model,
                    "display_name": row.display_name,
                    "max_context_size": row.max_context_size,
                    "max_output_size": row.max_output_size,
                    "capabilities": row.capabilities,
                    "support_efforts": row.support_efforts,
                    "default_effort": row.default_effort,
                    "reasoning_key": row.reasoning_key,
                    "enabled": row.enabled,
                }
                for row in s.scalars(select(ModelDefinitionRow)).all()
            }
            default_row = s.get(SystemSettingRow, KEY_DEFAULT_MODEL)
            return {
                "default_model": default_row.setting_value if default_row else "",
                "providers": providers,
                "models": models,
            }
