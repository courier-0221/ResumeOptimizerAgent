"""生产者与消费者共享的连接配置。

单独抽出来，保证 producer.py 和 consumer.py 连到同一个 Redis、同一个队列。
"""

REDIS_URL = "redis://localhost:6379/0"
QUEUE_NAME = "demo_queue"
