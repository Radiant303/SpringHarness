from pydantic_ai import ModelProfile
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.alibaba import AlibabaProvider
from pydantic_ai.providers.deepseek import DeepSeekProvider

from spring_harness.core.config.settings import (
    DASHSCOPE_API_KEY,
    DASHSCOPE_BASE_URL,
    DASHSCOPE_MODEL_NAME,
    DEEPSEEK_API_KEY,
    DEEPSEEK_MODEL_NAME,
)


def get_model():
    return get_dashscope_model()

def get_dashscope_model():
    return OpenAIChatModel(
        DASHSCOPE_MODEL_NAME,
        provider=AlibabaProvider(
            api_key=DASHSCOPE_API_KEY,
            base_url=DASHSCOPE_BASE_URL
        ),
        profile=ModelProfile(
            supports_json_schema_output=True,
            default_structured_output_mode='native',
        ),
    )


def get_deepseek_model():
    return OpenAIChatModel(
        DEEPSEEK_MODEL_NAME,
        provider=DeepSeekProvider(
            api_key=DEEPSEEK_API_KEY
        ),
        profile=ModelProfile(
            supports_json_object_output=True,
            default_structured_output_mode='prompted',
        ),
    )
