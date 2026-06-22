# ResumeOptimizerAgent

基于 LangChain + FastAPI + RQ 的简历优化服务：上传 PDF 简历，按目标岗位异步优化并生成报告。

## 技术栈

- **Web**：FastAPI + Uvicorn
- **任务队列**：Redis + RQ（异步处理耗时的优化任务）
- **存储**：SQLite（任务状态）+ 本地文件（简历/产物）
- **LLM**：LangChain（DeepSeek）
- **PDF**：pdfplumber（解析）+ WeasyPrint（生成）

## 一、环境安装

### 1. 准备 conda 环境

```bash
conda create -n cv python=3.12 -y
conda activate cv
```

### 2. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

### 3. 准备 Redis

`QUEUE_BACKEND=redis` 时需要 Redis 服务（`start.sh` 会自动拉起；若系统已有则自动复用）。

用 conda 安装 Redis：

```bash
conda install -c conda-forge redis-server -y
```

本地若不想装 Redis，可在 `.env` 设 `QUEUE_BACKEND=fake`，任务会在 API 进程内同步执行。

### 4. 配置 .env

在项目根目录创建 `.env`，关键配置项：

```dotenv
DEEPSEEK_API_KEY=你的key
QUEUE_BACKEND=redis        # redis 异步 / fake 同步自测
QUEUE_ASYNC=true
AGENT_MODE=real
SEND_EMAIL=false           # 是否发送结果邮件
REDIS_URL=redis://localhost:6379/0
DB_PATH=data/database.db
UPLOAD_DIR=data/uploads
TASK_DATA_DIR=data/task_data
MAX_UPLOAD_BYTES=10485760
# SEND_EMAIL=true 时需配置 SMTP_HOST / SMTP_PORT / SMTP_USERNAME / SMTP_PASSWORD ...
```

> 启动参数（API 地址/端口、Redis 端口、队列后端）的唯一来源是 `.env` + `src/common/config.py`。

## 二、使用 start.sh 管理服务

`start.sh` 统一管理 **redis / api / worker** 三个进程（后台运行，PID 存于 `.run/`，日志写入 `logs/`）。

```bash
chmod +x start.sh   # 首次赋予执行权限
```

### 常用命令

| 命令 | 说明 |
|---|---|
| `./start.sh start [all]` | 后台启动服务（默认 `all`） |
| `./start.sh stop [all]` | 停止服务（默认 `all`） |
| `./start.sh restart [all]` | 重启 |
| `./start.sh status` | 查看各服务状态（PID / 端口） |
| `./start.sh logs <服务>` | 实时跟踪日志（`tail -f`） |
| `./start.sh run <服务>` | 前台运行单个服务（调试用，`Ctrl+C` 退出） |

目标 `<服务>` 可为 `redis` / `api` / `worker`。

### 典型流程

```bash
# 启动全部（自动按 redis → worker → api 顺序拉起）
./start.sh start

# 查看状态
./start.sh status

# 跟踪 API 日志
./start.sh logs api

# 停止全部
./start.sh stop
```

### 行为说明

- **启动顺序**：`start all` 会先起 redis 并等待端口就绪，再起依赖它的 worker 和 api。
- **redis 复用**：若 redis 端口已在监听（系统/外部管理），则跳过启动，`stop` 也不会停它。
- **fake 后端**：`QUEUE_BACKEND=fake` 时 `start all` 仅启动 api（任务在 API 进程内同步执行，无需 redis/worker）。

### 日志位置

三个服务的标准输出/错误分别重定向到：

- `logs/redis.log`
- `logs/api.log`
- `logs/worker.log`

## 三、调试单服务（前台运行）

```bash
./start.sh run api      # 前台跑 API，方便看实时输出 / 断点调试
./start.sh run worker   # 前台跑 worker
```