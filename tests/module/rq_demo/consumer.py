"""Redis + RQ 演示 —— 消费者进程（consumer / worker）。

这是一个「独立的工人进程」：它连上 Redis，盯着 demo_queue 队列，
一旦有任务进来就取出来执行，然后把结果写回 Redis。

它和 producer.py 是两个完全独立的进程，彼此不直接通信，
全靠中间的 Redis 队列传递任务 —— 这正是 RQ 异步的核心。

────────────────────────────────────────────────────────────
运行（项目根目录 ResumeOptimizerAgent/ 下，确保 Redis 已启动）：

    python consumer.py

启动后它会一直阻塞等待任务（Ctrl+C 退出）。
再开另一个终端运行 producer.py 投递任务，就能看到这边打印执行日志。
────────────────────────────────────────────────────────────
"""

import os
import sys

# 确保项目根目录在 path 中，这样 worker 能 import 到 tests.rq_demo.jobs
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import redis
from rq import Queue, Worker

from settings import REDIS_URL, QUEUE_NAME


def main():
    # 1. 连接 Redis
    conn = redis.Redis.from_url(REDIS_URL)

    # 2. 创建一个 Worker，监听指定队列
    queue = Queue(QUEUE_NAME, connection=conn)
    worker = Worker([queue], connection=conn)

    print(f"[consumer] Worker 已启动，正在监听队列 '{QUEUE_NAME}' ... (Ctrl+C 退出)")

    # 3. 开始工作：这是个阻塞循环，会一直从队列取任务执行，直到进程被终止
    worker.work(with_scheduler=False)


if __name__ == "__main__":
    main()
