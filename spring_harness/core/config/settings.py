import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Self

import tomli as tomllib

CONFIG_PATH = Path.home() / ".springharness" / "config.toml"
def _load_toml_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Configuration file not found: {CONFIG_PATH}")
    with CONFIG_PATH.open("rb") as f:
        return tomllib.load(f)


def _from_dict(cls: type, data: dict[str, Any]) -> Any:
    if not data:
        return cls()

    if not hasattr(cls, "__annotations__"):
        return data

    annotations = getattr(cls, "__annotations__", {})
    result = {}

    for name, field_type in annotations.items():
        key_name = name.lstrip("_")
        if key_name not in data:
            continue

        value = data[key_name]
        origin = getattr(field_type, "__origin__", None)

        if hasattr(field_type, "__dataclass_fields__"):
            result[name] = _from_dict(field_type, value)
        elif origin is list and hasattr(field_type, "__args__"):
            item_type = field_type.__args__[0]
            if hasattr(item_type, "__dataclass_fields__"):
                result[name] = [_from_dict(item_type, item) for item in value]
            else:
                result[name] = value
        elif origin is dict and hasattr(field_type, "__args__"):
            result[name] = value
        else:
            result[name] = value

    return cls(**result)


class ConfigBase:
    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        private_name = f"_{name}"
        if private_name in self.__dict__:
            return getattr(self, private_name)
        raise AttributeError(f"'{self.__class__.__name__}' has no attribute '{name}'")

    def __setattr__(self, name: str, value: Any) -> None:
        if not name.startswith("_"):
            object.__setattr__(self, f"_{name}", value)
        else:
            object.__setattr__(self, name, value)

    def to_dict(self) -> dict[str, Any]:
        result = {}
        for key, value in self.__dict__.items():
            if key.startswith("_"):
                public_key = key[1:]
                if hasattr(value, "to_dict"):
                    result[public_key] = value.to_dict()
                elif isinstance(value, list):
                    result[public_key] = [
                        item.to_dict() if hasattr(item, "to_dict") else item
                        for item in value
                    ]
                elif isinstance(value, dict):
                    result[public_key] = {
                        k: v.to_dict() if hasattr(v, "to_dict") else v
                        for k, v in value.items()
                    }
                else:
                    result[public_key] = value
        return result


@dataclass
class Provider(ConfigBase):
    _type: str
    _api_key: str
    _base_url: str | None = None

    @property
    def type(self) -> str:
        return self._type

    @property
    def api_key(self) -> str:
        return self._api_key

    @property
    def base_url(self) -> str | None:
        return self._base_url


@dataclass
class Model(ConfigBase):
    _provider: str
    _model: str
    _max_context_size: int
    _display_name: str
    _max_output_size: int = 0
    _capabilities: list[str] = field(default_factory=list)
    _support_efforts: list[str] = field(default_factory=list)
    _default_effort: str = ""
    _reasoning_key: str | None = None

    @property
    def provider(self) -> str:
        return self._provider

    @property
    def model(self) -> str:
        return self._model

    @property
    def max_context_size(self) -> int:
        return self._max_context_size

    @property
    def max_output_size(self) -> int:
        return self._max_output_size

    @property
    def display_name(self) -> str:
        return self._display_name

    @property
    def capabilities(self) -> list[str]:
        return self._capabilities

    @property
    def support_efforts(self) -> list[str]:
        return self._support_efforts

    @property
    def default_effort(self) -> str:
        return self._default_effort

    @property
    def reasoning_key(self) -> str | None:
        return self._reasoning_key


@dataclass
class LoopControl(ConfigBase):
    _max_retries_per_step: int = 3
    _reserved_context_size: int = 50000

    @property
    def max_retries_per_step(self) -> int:
        return self._max_retries_per_step

    @property
    def reserved_context_size(self) -> int:
        return self._reserved_context_size


@dataclass
class Thinking(ConfigBase):
    _enabled: bool = True
    _effort: str = "high"

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def effort(self) -> str:
        return self._effort


@dataclass
class SecondaryModel(ConfigBase):
    _model: str = ""
    _default_effort: str = "on"

    @property
    def model(self) -> str:
        return self._model

    @property
    def default_effort(self) -> str:
        return self._default_effort


@dataclass
class Log(ConfigBase):
    _log_level: str = "INFO"

    @property
    def log_level(self) -> str:
        return self._log_level


@dataclass
class Config(ConfigBase):
    _default_model: str
    _loop_control: LoopControl
    _thinking: Thinking
    _providers: dict[str, Provider]
    _models: dict[str, Model]
    _secondary_model: SecondaryModel
    _log: Log

    @classmethod
    def from_toml(cls, config_path: Path | None = None) -> Self:
        """从 TOML 文件加载配置"""
        data = _load_toml_config() if config_path is None else _load_toml_config_from_path(config_path)

        providers = {
            name: _from_dict(Provider, pdata)
            for name, pdata in data.get("providers", {}).items()
        }

        models = {
            name: _from_dict(Model, mdata)
            for name, mdata in data.get("models", {}).items()
        }


        log_data = data.get("log", {})
        log = Log(
            _log_level=log_data.get("log_level", "INFO"),
        )

        return cls(
            _default_model=data.get("default_model", ""),
            _loop_control=_from_dict(LoopControl, data.get("loop_control", {})),
            _thinking=_from_dict(Thinking, data.get("thinking", {})),
            _providers=providers,
            _models=models,
            _secondary_model=_from_dict(SecondaryModel, data.get("secondary_model", {})),
            _log=log,
        )

    def get_model(self, model_id: str) -> Model | None:
        """获取模型配置"""
        return self._models.get(model_id)

    def get_provider(self, provider_name: str) -> Provider | None:
        """获取 Provider 配置"""
        return self._providers.get(provider_name)

    def get_provider_by_model(self, model_id: str) -> Provider | None:
        """通过模型 ID 获取对应的 Provider"""
        model = self.get_model(model_id)
        if model:
            return self.get_provider(model.provider)
        return None

    def get_models_by_provider(self, provider_name: str) -> list[str]:
        """获取指定 Provider 的所有模型 ID"""
        return [
            mid for mid, model in self._models.items()
            if model.provider == provider_name
        ]

    def get_models_with_capability(self, capability: str) -> list[str]:
        """获取支持特定能力的模型 ID 列表"""
        return [
            mid for mid, model in self._models.items()
            if capability in model.capabilities
        ]

    def get_default_model_config(self) -> Model | None:
        """获取默认模型配置"""
        return self.get_model(self._default_model)

    def set_default_model(self, model_id: str) -> None:
        """切换默认模型：更新内存，并把 default_model 行写回 config.toml。"""
        if model_id not in self._models:
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
        self._default_model = model_id


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
        return list(self._models.keys())

    def list_providers(self) -> list[str]:
        """列出所有 Provider 名称"""
        return list(self._providers.keys())

    def get_secondary_model_config(self) -> dict[str, Any]:
        """获取子模型配置"""
        return {
            "model": self._secondary_model.model,
            "default_effort": self._secondary_model.default_effort,
        }

    @property
    def default_model(self) -> str:
        """默认模型 ID"""
        return self._default_model

    @property
    def loop_control(self) -> LoopControl:
        return self._loop_control

    @property
    def thinking(self) -> Thinking:
        return self._thinking

    @property
    def providers(self) -> dict[str, Provider]:
        return self._providers

    @property
    def models(self) -> dict[str, Model]:
        return self._models

    @property
    def secondary_model(self) -> SecondaryModel:
        return self._secondary_model

    @property
    def log(self) -> Log:
        return self._log


def _load_toml_config_from_path(config_path: Path) -> dict[str, Any]:
    """从指定路径加载 TOML 配置"""
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    with config_path.open("rb") as f:
        return tomllib.load(f)


config = Config.from_toml()

default_model = config.default_model
models = config.models
providers = config.providers
loop_control = config.loop_control
thinking = config.thinking
secondary_model = config.secondary_model
log = config.log
