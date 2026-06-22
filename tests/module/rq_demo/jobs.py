"""RQ 演示用的「任务函数」。

RQ 的 worker 是独立进程，它通过「函数的导入路径」来找到并执行任务，
所以任务函数必须放在一个可被 import 的模块里（不能是 __main__ 里的局部函数）。
"""

import time


def slow_add(a: int, b: int) -> int:
    """模拟一个耗时计算：sleep 几秒后返回 a + b。"""
    print(f"[worker] 开始计算 {a} + {b} ...")
    time.sleep(3)
    result = a + b
    print(f"[worker] 计算完成，结果 = {result}")
    return result


def greet(name: str) -> str:
    """一个更快的任务，演示不同参数。"""
    time.sleep(1)
    return f"你好，{name}！"


def boom() -> None:
    """故意抛异常，演示任务失败时 RQ 如何处理。"""
    time.sleep(1)
    raise ValueError("我故意失败了 💥")
