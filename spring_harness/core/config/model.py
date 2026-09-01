from typing import Any

from pydantic_ai import ModelProfile
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.alibaba import AlibabaProvider
from pydantic_ai.providers.deepseek import DeepSeekProvider
from pydantic_ai.providers.openai import OpenAIProvider

from spring_harness.core.config.settings import config


class Setting:
    def __init__(self) -> None:
        self.config = config
        self._providers = {
            "openai": self._openai,
            "alibaba": self._alibaba,
            "deepseek": self._deepseek,
        }

    def get_model(self, model_name: str | None = None) -> Model:
        model_name = model_name or self.config.default_model
        model_config = self.config.get_model(model_name)

        if not model_config:
            raise ValueError(f"模型 '{model_name}' 不存在")

        provider_config = self.config.get_provider(model_config.provider)
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

    @staticmethod
    def _profile(native: bool = False) -> ModelProfile:
        """统一的 profile 配置"""
        return ModelProfile(
            supports_json_schema_output=native,
            supports_json_object_output=not native,
            default_structured_output_mode='native' if native else 'prompted',
        )

    def list_models(self) -> list[str]:
        """列出所有可用模型"""
        return list(self.config.models.keys())

    def list_providers(self) -> list[str]:
        """列出所有可用 Provider"""
        return list(self.config.providers.keys())


# 全局实例
setting = Setting()
get_model = setting.get_model
