"""统一服务入口。
用法:
    python -m src.main api       # 启动 API 服务 (uvicorn)
    python -m src.main worker    # 启动任务 worker (RQ)
    python -m src.main all       # 同时启动 worker(子进程) + api(前台)
"""

import argparse
import multiprocessing
import sys

from src.common.config import Config
from src.common.logger import logger, setup_logger


def run_api(config: Config) -> None:
    import uvicorn

    uvicorn.run(
        "src.api.app:app",
        host=config.API_HOST,
        port=config.API_PORT,
        reload=config.API_RELOAD,
        log_level=config.LOG_LEVEL.lower(),
    )


def run_worker(config: Config) -> None:
    # 复用现有 worker 入口，保持队列/连接逻辑单点
    from src.api.worker.run_worker import main as worker_main

    worker_main()


def run_all(config: Config) -> None:
    """同时启动 worker(子进程) + api(前台)。退出时一并回收 worker。"""
    if config.QUEUE_BACKEND == "fake":
        logger.info("QUEUE_BACKEND=fake，任务在 API 进程内同步执行，仅启动 API")
        run_api(config)
        return

    # 预检 redis 连通性：连不上则不盲目拉起 worker（否则它会静默崩溃）
    from src.api.worker.task_queue import get_redis

    try:
        get_redis().ping()
    except Exception as exc:
        logger.error(
            "无法连接 Redis（{}）：{}。请先启动 Redis（如 ./manage.sh start redis）后重试。",
            config.REDIS_URL,
            exc,
        )
        return

    if config.API_RELOAD:
        logger.warning("all 模式不支持 API_RELOAD 热重载，已忽略该选项")

    worker_proc = multiprocessing.Process(
        target=run_worker, args=(config,), name="rq-worker", daemon=True
    )
    worker_proc.start()
    logger.info("worker 子进程已启动 (pid {})", worker_proc.pid)

    try:
        run_api(config)
    finally:
        if worker_proc.is_alive():
            logger.info("正在停止 worker 子进程 (pid {}) ...", worker_proc.pid)
            worker_proc.terminate()
            worker_proc.join(timeout=10)
            if worker_proc.is_alive():
                worker_proc.kill()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="resume-optimizer", description="ResumeOptimizerAgent 服务入口"
    )
    sub = parser.add_subparsers(dest="service", required=True)
    sub.add_parser("api", help="启动 API 服务 (uvicorn)")
    sub.add_parser("worker", help="启动任务 worker (RQ)")
    sub.add_parser("all", help="同时启动 worker(子进程) + api(前台)")
    args = parser.parse_args(argv)

    config = Config()
    setup_logger(level=config.LOG_LEVEL, log_file=config.LOG_FILE)

    if args.service == "api":
        run_api(config)
    elif args.service == "worker":
        run_worker(config)
    elif args.service == "all":
        run_all(config)
    return 0


if __name__ == "__main__":
    sys.exit(main())
