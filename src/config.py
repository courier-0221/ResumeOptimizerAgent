import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    MODEL_NAME: str = "deepseek-v4-pro"
    TEMPERATURE: float = 0.3
    MAX_TOKENS: int = 8192
    OUTPUT_DIR: str = "output"
    TEMPLATE_DIR: str = "templates"
    # 深度思考（DeepSeek Thinking）
    ENABLE_THINKING: bool = False
    # 日志
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "DEBUG")
    LOG_FILE: str = os.getenv("LOG_FILE", "")  # 留空则只输出到终端
