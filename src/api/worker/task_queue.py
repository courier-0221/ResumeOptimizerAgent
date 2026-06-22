import redis
from rq import Queue

from src.common.config import Config

config = Config()


def get_redis():
    """获取 Redis 连接。fake 后端用于本地无 Redis 时的同步自测。"""
    if config.QUEUE_BACKEND == "fake":
        import fakeredis

        return fakeredis.FakeStrictRedis()
    return redis.Redis.from_url(config.REDIS_URL)


def get_queue() -> Queue:
    """获取 RQ 队列。

    - redis 后端：is_async 由 QUEUE_ASYNC 控制（生产用 True，配独立 worker）。
    - fake 后端：强制同步执行（FakeRedis 不跨进程共享，无法异步）。
    """
    is_async = config.QUEUE_ASYNC and config.QUEUE_BACKEND != "fake"
    return Queue(
        config.QUEUE_NAME,
        connection=get_redis(),
        is_async=is_async,
        default_timeout=config.TASK_TIMEOUT,
    )
