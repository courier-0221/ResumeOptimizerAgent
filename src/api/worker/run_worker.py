import os
import sys

# 确保项目根目录在 path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from rq import Worker

from src.common.config import Config
from src.common.logger import logger, setup_logger
from src.api.worker.task_queue import get_redis


def main():
    config = Config()
    setup_logger(level=config.LOG_LEVEL, log_file=config.LOG_FILE)

    if config.QUEUE_BACKEND == "fake":
        logger.error(
            "QUEUE_BACKEND=fake 为同步执行模式，无需独立 worker。"
            "如需异步处理，请设置 QUEUE_BACKEND=redis 并启动 Redis 服务。"
        )
        return

    redis_conn = get_redis()
    logger.info("RQ Worker 启动，监听队列: {}", config.QUEUE_NAME)
    worker = Worker([config.QUEUE_NAME], connection=redis_conn)
    worker.work(with_scheduler=False)


if __name__ == "__main__":
    main()
