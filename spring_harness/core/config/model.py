from typing import Any, Protocol

from pydantic_ai import ModelProfile
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIResponsesModel
from pydantic_ai.providers.alibaba import AlibabaProvider
from pydantic_ai.providers.deepseek import DeepSeekProvider
from pydantic_ai.providers.openai import OpenAIProvider

from spring_harness.core.config.settings import Model as ModelConfig
from spring_harness.core.config.settings import Provider as ProviderConfig
from spring_harness.core.config.settings import config


class ModelCatalog(Protocol):
    """模型配置目录：模型/Provider 定义与默认模型的来源。

    本地入口读 config.toml；云端入口启动时换成直读 MySQL，即改即生效。
    """

    def default_model(self) -> str:
        """默认模型 ID。"""
        ...

    def get_model_config(self, model_id: str) -> ModelConfig | None:
        """按 ID 取模型定义（含停用的）。"""
        ...

    def get_provider_config(self, provider_name: str) -> ProviderConfig | None:
        """按名取 Provider。"""
        ...

    def list_model_configs(self) -> list[tuple[str, ModelConfig]]:
        """列出启用状态的 (模型 ID, 定义)。"""
        ...


class TomlCatalog:
    """config.toml 目录：providers/models/default_model 全部来自配置文件。"""

    def default_model(self) -> str:
        return config.default_model

    def get_model_config(self, model_id: str) -> ModelConfig | None:
        return config.get_model(model_id)

    def get_provider_config(self, provider_name: str) -> ProviderConfig | None:
        return config.get_provider(provider_name)

    def list_model_configs(self) -> list[tuple[str, ModelConfig]]:
        return list(config.models.items())


class Setting:
    def __init__(self) -> None:
        self._catalog: ModelCatalog = TomlCatalog()
        self._providers = {
            "openai": self._openai,
            "alibaba": self._alibaba,
            "deepseek": self._deepseek,
            "responses": self._responses,
        }

    def set_catalog(self, catalog: ModelCatalog) -> None:
        """切换模型配置来源（云端入口启动时换成 DB 目录）。"""
        self._catalog = catalog

    def default_model(self) -> str:
        """默认模型 ID。"""
        return self._catalog.default_model()

    def get_model(self, model_name: str | None = None) -> Model:
        model_name = model_name or self._catalog.default_model()
        model_config = self._catalog.get_model_config(model_name)

        if not model_config:
            raise ValueError(f"模型 '{model_name}' 不存在")

        provider_config = self._catalog.get_provider_config(model_config.provider)
        if not provider_config:
            raise ValueError(f"Provider '{model_config.provider}' 不存在")

        provider_type = provider_config.type
        creator = self._providers.get(provider_type)

        if not creator:
            raise ValueError(f"不支持的 Provider 类型: {provider_type}")

        return creator(
            model_name=model_config.model,
            provider_config=provider_config,
            model_config=model_config,
        )

    def _openai(self, model_name: str, provider_config: Any, model_config: Any) -> Model:
        return OpenAIChatModel(
            model_name,
            provider=OpenAIProvider(
                base_url=provider_config.base_url,
                api_key=provider_config.api_key,
            ),
            profile=self._profile(),
        )

    def _alibaba(self, model_name: str, provider_config: Any, model_config: Any) -> Model:
        return OpenAIChatModel(
            model_name,
            provider=AlibabaProvider(
                base_url=provider_config.base_url,
                api_key=provider_config.api_key,
            ),
            profile=self._profile(native=True),
        )

    def _deepseek(self, model_name: str, provider_config: Any, model_config: Any) -> Model:
        return OpenAIChatModel(
            model_name,
            provider=DeepSeekProvider(
                api_key=provider_config.api_key,
            ),
            profile=self._profile(),
        )

    def _responses(self, model_name: str, provider_config: Any, model_config: Any) -> Model:
        return OpenAIResponsesModel(
            model_name,
            provider=OpenAIProvider(
                base_url=provider_config.base_url,
                api_key=provider_config.api_key,
            ),
            profile=self._profile(),
        )

    @staticmethod
    def _profile(native: bool = False) -> ModelProfile:
        """统一的 profile 配置"""
        return ModelProfile(
            supports_json_schema_output=native,
            supports_json_object_output=not native,
            default_structured_output_mode='native' if native else 'prompted',
        )

    def list_models(self) -> list[str]:
        """列出所有可用模型（启用状态）"""
        return [mid for mid, _ in self._catalog.list_model_configs()]

    def list_model_configs(self) -> list[tuple[str, ModelConfig]]:
        """列出启用状态的 (模型 ID, 定义)（picker/initialize 用）。"""
        return self._catalog.list_model_configs()

    def list_providers(self) -> list[str]:
        """列出所有可用 Provider（Toml 目录专用；DB 目录不提供全量列举）"""
        return list(config.providers.keys())

    def get_model_config(self, model_name: str | None = None) -> ModelConfig:
        model_name = model_name or self._catalog.default_model()
        model_config = self._catalog.get_model_config(model_name)
        if not model_config:
            raise ValueError(f"模型 '{model_name}' 不存在")
        return model_config

# 全局实例
setting = Setting()
get_model = setting.get_model
get_model_config = setting.get_model_config
set_catalog = setting.set_catalog
