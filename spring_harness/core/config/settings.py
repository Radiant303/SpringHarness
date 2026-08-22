import os
from pathlib import Path

from dotenv import load_dotenv


def _load_dotenv() -> None:
    env_file = Path(__file__).resolve().parents[3] / ".env"
    if not load_dotenv(env_file, override=False):
        raise FileNotFoundError(f"配置文件未找到: {env_file}")


_load_dotenv()

# 模型和API配置

DASHSCOPE_BASE_URL: str = os.getenv("DASHSCOPE_BASE_URL","")
DASHSCOPE_API_KEY: str = os.getenv("DASHSCOPE_API_KEY","")
DASHSCOPE_MODEL_NAME: str = os.getenv("DASHSCOPE_MODEL_NAME","")


DEEPSEEK_MODEL_NAME: str = os.getenv("DEEPSEEK_MODEL_NAME","")
DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY","")

# 日志配置
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
BASE_DIR = Path(__file__).resolve().parents[3]
LOG_FILE: str = os.getenv("LOG_FILE", str(BASE_DIR / "logs" / "app.log"))
