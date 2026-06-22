"""
统一日志配置模块 — 基于 loguru。

用法:
    from src.common.logger import logger

    logger.info("正在处理...")
    logger.debug("详细数据: {}", data)
    logger.success("完成!")
    logger.warning("警告信息")
    logger.error("错误信息")
"""

import sys
from loguru import logger as _logger


def setup_logger(level: str = "INFO", log_file: str = "") -> None:
    """配置 loguru 日志。

    Args:
        level: 日志级别 (DEBUG / INFO / WARNING / ERROR)
        log_file: 可选的文件路径，日志同时写入文件（支持轮转）
    """
    # 移除默认 handler
    _logger.remove()

    # 控制台输出：彩色格式
    _logger.add(
        sys.stderr,
        level=level,
        format=(
            "<green>{time:HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<level>{message}</level>"
        ),
        colorize=True,
    )

    # 文件输出（如果指定）
    if log_file:
        _logger.add(
            log_file,
            level="DEBUG",  # 文件记录更详细
            format=(
                "{time:YYYY-MM-DD HH:mm:ss} | "
                "{level: <8} | "
                "{name}:{function}:{line} | "
                "{message}"
            ),
            rotation="10 MB",   # 单文件 10MB 自动轮转
            retention="7 days",  # 保留最近 7 天
            encoding="utf-8",
        )


# 暴露 logger 给外部直接 import
logger = _logger
