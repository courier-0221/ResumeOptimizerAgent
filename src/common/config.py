import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

# core 的 PDF 渲染模板目录（绝对路径，不依赖运行时 cwd）
_CORE_TEMPLATE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "core",
    "templates",
)


def _get_bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _get_int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _get_str_env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value is None:
        return default
    return value


@dataclass
class Config:
    DEEPSEEK_API_KEY: str = _get_str_env("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL: str = _get_str_env("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    MODEL_NAME: str = _get_str_env("MODEL_NAME", "deepseek-v4-pro")
    TEMPERATURE: float = _get_int_env("TEMPERATURE", 0.3)
    MAX_TOKENS: int = _get_int_env("MAX_TOKENS", 8192)
    OUTPUT_DIR: str = _get_str_env("OUTPUT_DIR", "output")
    TEMPLATE_DIR: str = _get_str_env("TEMPLATE_DIR", _CORE_TEMPLATE_DIR)
    # 深度思考（DeepSeek Thinking）
    # 思考模式开关：True -> enabled，False -> disabled（DeepSeek 默认 enabled）
    ENABLE_THINKING: bool = _get_bool_env("ENABLE_THINKING", False)
    # 思考强度：仅在思考模式开启时生效。可选 "high" / "max"
    # 注意：low/medium 会被映射为 high，xhigh 会被映射为 max
    REASONING_EFFORT: str = _get_str_env("REASONING_EFFORT", "high")

    # 日志
    LOG_LEVEL: str = _get_str_env("LOG_LEVEL", "DEBUG")  # 可选 "DEBUG" / "INFO" / "WARNING" / "ERROR"
    LOG_FILE: str = _get_str_env("LOG_FILE", "")  # 留空则只输出到终端

    # 邮件发送（SMTP）
    SMTP_HOST: str = _get_str_env("SMTP_HOST", "")
    SMTP_PORT: int = _get_int_env("SMTP_PORT", 587)
    SMTP_USERNAME: str = _get_str_env("SMTP_USERNAME", "")
    SMTP_PASSWORD: str = _get_str_env("SMTP_PASSWORD", "")
    SMTP_FROM: str = _get_str_env("SMTP_FROM", "") or _get_str_env("SMTP_USERNAME", "")
    SMTP_USE_TLS: bool = _get_bool_env("SMTP_USE_TLS", True)
    SMTP_USE_SSL: bool = _get_bool_env("SMTP_USE_SSL", False)

    # ===== Web / API 服务 =====
    API_HOST: str = _get_str_env("API_HOST", "0.0.0.0")
    API_PORT: int = _get_int_env("API_PORT", 8000)
    # 开发热重载：True 时 uvicorn 监听代码变更自动重启（生产请保持 False）
    API_RELOAD: bool = _get_bool_env("API_RELOAD", False)

    # ===== 本地存储（v1 使用本地磁盘，不接 OSS）=====
    UPLOAD_DIR: str = _get_str_env("UPLOAD_DIR", "data/uploads")
    TASK_DATA_DIR: str = _get_str_env("TASK_DATA_DIR", "data/tasks")
    DB_PATH: str = _get_str_env("DB_PATH", "data/app.db")
    MAX_UPLOAD_BYTES: int = _get_int_env("MAX_UPLOAD_BYTES", 10 * 1024 * 1024)

    # ===== 任务队列（RQ + Redis）=====
    REDIS_URL: str = _get_str_env("REDIS_URL", "redis://localhost:6379/0")
    QUEUE_NAME: str = _get_str_env("QUEUE_NAME", "resume")
    # 队列后端：redis（生产，需 Redis + 独立 worker）| fake（本地无 Redis 时同步执行，便于自测）
    QUEUE_BACKEND: str = _get_str_env("QUEUE_BACKEND", "redis")
    QUEUE_ASYNC: bool = _get_bool_env("QUEUE_ASYNC", True)
    TASK_TIMEOUT: int = _get_int_env("TASK_TIMEOUT", 1800)

    # ===== 任务执行模式 =====
    # real：调用真实 ResumeOptimizerAgent（需 DEEPSEEK_API_KEY）
    # mock：生成占位 PDF，不调 LLM，便于无密钥验证 web 链路
    AGENT_MODE: str = _get_str_env("AGENT_MODE", "real")
    # 是否真实发送邮件（自测时可设为 false）
    SEND_EMAIL: bool = _get_bool_env("SEND_EMAIL", True)
