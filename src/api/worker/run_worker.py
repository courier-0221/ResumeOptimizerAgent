import os
import sys

# macOS 修复：RQ 默认 Worker 每个任务都会 fork() 出 work-horse 子进程执行，
# 而 macOS 的 Objective-C 运行时在 fork 后再初始化时会直接 SIGABRT 崩溃
# （日志表现为 "objc[...] +[__NSCFConstantString initialize] ... fork() ... Crashing instead"，
# 任务随即 failed: Work-horse terminated unexpectedly, signal 6）。
# OBJC_DISABLE_INITIALIZE_FORK_SAFETY 在多线程 + 第三方库场景下并不总能压住，
# 因此在 macOS 上改用不 fork 的 SimpleWorker（任务在 worker 进程内直接执行），彻底规避。
if sys.platform == "darwin":
    os.environ.setdefault("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES")

# 确保项目根目录在 path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from rq import SimpleWorker, Worker

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
    # macOS 上用 SimpleWorker（不 fork），其余平台保留默认 fork 模型以获得进程隔离。
    worker_cls = SimpleWorker if sys.platform == "darwin" else Worker
    logger.info(
        "RQ Worker 启动，监听队列: {}（{}）",
        config.QUEUE_NAME,
        worker_cls.__name__,
    )
    worker = worker_cls([config.QUEUE_NAME], connection=redis_conn)
    worker.work(with_scheduler=False)


if __name__ == "__main__":
    main()
