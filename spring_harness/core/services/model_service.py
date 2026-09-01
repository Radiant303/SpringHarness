from pydantic_ai.models import Model

from spring_harness.core.config.model import get_model
from spring_harness.core.config.settings import config


class MODEL:
    def __init__(self) -> None:
        self.config = config
        self.get_model = get_model

    def resolve_model(self, model_id: str) -> Model:
        """将模型 ID解析为 Pydantic AI Model。"""
        if model_id not in self.config.models:
            raise ValueError(f"未知的 ACP 模型: {model_id}")

        return self.get_model(model_id)

model = MODEL()
resolve_model = model.resolve_model
