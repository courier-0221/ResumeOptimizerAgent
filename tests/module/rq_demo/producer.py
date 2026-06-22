"""Redis + RQ 演示 —— 生产者进程（producer）。

这是一个「派活的人」：它连上 Redis，把任务一个个塞进 demo_queue 队列，
然后不断轮询，观察任务从「排队」到「执行中」再到「完成/失败」的过程。

它自己**不执行任务**，真正干活的是 consumer.py（独立 worker 进程）。

────────────────────────────────────────────────────────────
运行步骤（项目根目录 ResumeOptimizerAgent/ 下，确保 Redis 已启动）：

  终端 1（消费者，先启动，保持运行）：
      python consumer.py

  终端 2（生产者，投递任务）：
      python producer.py

  观察：终端 1 打印任务执行日志，终端 2 每秒刷新各任务状态。
────────────────────────────────────────────────────────────
"""

import os
import sys
import time

# 确保项目根目录在 path 中，这样能 import 到 tests.rq_demo.jobs
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import redis
from rq import Queue

from jobs import slow_add, greet, boom
from settings import REDIS_URL, QUEUE_NAME


def main():
    # 1. 连接 Redis，创建队列对象
    conn = redis.Redis.from_url(REDIS_URL)
    queue = Queue(QUEUE_NAME, connection=conn)
    print(f"[producer] 已连接队列 '{QUEUE_NAME}'，当前排队任务数: {len(queue)}\n")

    # 2. 投递任务：enqueue(函数, *args) —— 立刻返回 Job 对象，不会阻塞等待结果
    job1 = queue.enqueue(slow_add, 3, 4)                       # 位置参数
    job2 = queue.enqueue(greet, name="小明")                    # 关键字参数
    job3 = queue.enqueue(boom)                                # 会失败的任务
    job4 = queue.enqueue(slow_add, 100, 200, job_timeout=10)  # 自定义超时

    jobs = {"slow_add(3,4)": job1, "greet(小明)": job2, "boom()": job3, "slow_add(100,200)": job4}

    print("[producer] 已投递 4 个任务，job_id 如下：")
    for name, job in jobs.items():
        print(f"  - {name:18s} -> {job.id}")
    print()

    # 3. 轮询任务状态，直到全部结束（成功 finished / 失败 failed）
    print("[producer] 开始轮询任务状态（每秒一次）...\n")
    while True:
        lines = []
        all_done = True
        for name, job in jobs.items():
            status = job.get_status(refresh=True)   # queued / started / finished / failed
            lines.append(f"  {name:18s} 状态={status:9s} 结果={job.result}")
            if status not in ("finished", "failed"):
                all_done = False
        print("\n".join(lines))
        print("-" * 60)
        if all_done:
            break
        time.sleep(1)

    # 4. 展示最终结果
    print("\n[producer] === 全部任务结束，最终结果 ===")
    for name, job in jobs.items():
        if job.is_finished:
            print(f"  ✅ {name:18s} -> 返回值: {job.result}")
        elif job.is_failed:
            # 失败任务的异常信息保存在 exc_info 里
            print(f"  ❌ {name:18s} -> 执行失败（详见 consumer 日志 / job.exc_info）")


if __name__ == "__main__":
    main()
