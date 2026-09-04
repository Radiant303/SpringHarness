import re
import tomllib
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel, ConfigDict

CONFIG_PATH = Path.home() / ".springharness" / "config.toml"


def _load_toml_config(config_path: Path) -> dict[str, Any]:
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    with config_path.open("rb") as f:
        return tomllib.load(f)


class ConfigBase(BaseModel):
    # 打错 key 直接报错，不静默忽略
    model_config = ConfigDict(extra="forbid")


class Provider(ConfigBase):
    type: str
    api_key: str
    base_url: str | None = None


class Model(ConfigBase):
    provider: str
    model: str
    max_context_size: int
    display_name: str
    max_output_size: int = 0
    capabilities: list[str] = []
    support_efforts: list[str] = []
    default_effort: str = ""
    reasoning_key: str | None = None


class LoopControl(ConfigBase):
    max_retries_per_step: int = 3
    reserved_context_size: int = 50000


class Thinking(ConfigBase):
    enabled: bool = True
    effort: str = "high"


class SecondaryModel(ConfigBase):
    model: str = ""
    default_effort: str = "on"


class Log(ConfigBase):
    log_level: str = "INFO"


class SubAgentConfig(ConfigBase):
    model: str = ""   # 为空 = 继承主 agent 当前模型

class Config(ConfigBase):
    default_model: str = ""
    loop_control: LoopControl = LoopControl()
    thinking: Thinking = Thinking()
    providers: dict[str, Provider] = {}
    models: dict[str, Model] = {}
    secondary_model: SecondaryModel = SecondaryModel()
    log: Log = Log()
    subagents: dict[str, SubAgentConfig] = {}

    @classmethod
    def from_toml(cls, config_path: Path | None = None) -> Self:
        """从 TOML 文件加载配置"""
        data = _load_toml_config(config_path or CONFIG_PATH)
        return cls.model_validate(data)

    def get_model(self, model_id: str) -> Model | None:
        """获取模型配置"""
        return self.models.get(model_id)

    def get_provider(self, provider_name: str) -> Provider | None:
        """获取 Provider 配置"""
        return self.providers.get(provider_name)

    def get_provider_by_model(self, model_id: str) -> Provider | None:
        """通过模型 ID 获取对应的 Provider"""
        model = self.get_model(model_id)
        if model:
            return self.get_provider(model.provider)
        return None

    def get_models_by_provider(self, provider_name: str) -> list[str]:
        """获取指定 Provider 的所有模型 ID"""
        return [
            mid for mid, model in self.models.items()
            if model.provider == provider_name
        ]

    def get_models_with_capability(self, capability: str) -> list[str]:
        """获取支持特定能力的模型 ID 列表"""
        return [
            mid for mid, model in self.models.items()
            if capability in model.capabilities
        ]

    def get_default_model_config(self) -> Model | None:
        """获取默认模型配置"""
        return self.get_model(self.default_model)

    def set_default_model(self, model_id: str) -> None:
        """切换默认模型：更新内存，并把 default_model 行写回 config.toml。"""
        if model_id not in self.models:
            raise ValueError(f"模型 '{model_id}' 不存在")
        text = CONFIG_PATH.read_text(encoding="utf-8")
        new_text, n = re.subn(
            r"(?m)^default_model\s*=.*$",
            f'default_model = "{model_id}"',
            text,
        )
        if n == 0:
            raise ValueError(f"{CONFIG_PATH} 中缺少 default_model 配置项")
        CONFIG_PATH.write_text(new_text, encoding="utf-8")
        self.default_model = model_id

    def get_model_full_config(self, model_id: str) -> dict[str, Any]:
        """获取模型的完整配置（包含 Provider 信息）"""
        model = self.get_model(model_id)
        if not model:
            return {}

        provider = self.get_provider(model.provider)
        return {
            "model_id": model_id,
            "model": model.model,
            "provider": model.provider,
            "provider_type": provider.type if provider else "",
            "max_context_size": model.max_context_size,
            "max_output_size": model.max_output_size,
            "display_name": model.display_name,
            "capabilities": model.capabilities,
            "support_efforts": model.support_efforts,
            "default_effort": model.default_effort,
            "reasoning_key": model.reasoning_key,
            "api_key": provider.api_key if provider else "",
            "base_url": provider.base_url if provider else "",
        }

    def list_models(self) -> list[str]:
        """列出所有模型 ID"""
        return list(self.models.keys())

    def list_providers(self) -> list[str]:
        """列出所有 Provider 名称"""
        return list(self.providers.keys())

    def get_secondary_model_config(self) -> dict[str, Any]:
        """获取子模型配置"""
        return {
            "model": self.secondary_model.model,
            "default_effort": self.secondary_model.default_effort,
        }


config = Config.from_toml()

default_model = config.default_model
models = config.models
providers = config.providers
loop_control = config.loop_control
thinking = config.thinking
secondary_model = config.secondary_model
log = config.log
