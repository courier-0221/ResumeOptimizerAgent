#!/usr/bin/env bash
#
# ResumeOptimizerAgent 服务管理脚本
#
# 用法:
#   ./manage.sh start [redis|api|worker|all]   # 后台启动服务（默认 all）
#   ./manage.sh stop  [redis|api|worker|all]   # 停止服务（默认 all）
#   ./manage.sh restart [redis|api|worker|all] # 重启
#   ./manage.sh status                         # 查看各服务状态
#   ./manage.sh logs  [redis|api|worker]       # 跟踪日志（tail -f）
#   ./manage.sh run   [redis|api|worker]       # 前台运行单个服务（调试用，Ctrl+C 退出）
#
# 说明:
#   - api / worker 实际由 `python -m src.main` 启动，启动参数读自 .env / Config。
#   - redis 若已在端口上运行（系统/外部管理）则自动跳过启动，stop 也不会停它。
#   - QUEUE_BACKEND=fake 时 `start all` 仅启动 api（任务在 API 进程内同步执行，
#     无需 redis / worker）。
#
# 依赖:
#   - conda 环境 cv（含 uvicorn / rq 等 Python 依赖）
#   - redis 服务（系统自带或单独启动；本脚本不负责安装）
#   - 工程根目录下的 .env（DEEPSEEK_API_KEY、SMTP、QUEUE_BACKEND 等）
#
set -euo pipefail

# ---------------------------------------------------------------------------
# 基础路径与配置
# ---------------------------------------------------------------------------
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

CONDA_ENV="${CONDA_ENV:-cv}"
# 导出，确保 nohup 子 shell 中 activate_env 能读到（否则 conda activate "" 会切回 base）
export CONDA_ENV
RUN_DIR="$PROJECT_ROOT/.run"      # pid 文件目录
LOG_DIR="$PROJECT_ROOT/logs"      # 日志目录
mkdir -p "$RUN_DIR" "$LOG_DIR"

# 启动参数的唯一事实来源是 .env / src/common/config.py。
# 这里仅保留占位，真实值在 load_config 中由 Python Config 读取后填充。
API_HOST=""
API_PORT=""
REDIS_PORT=""
QUEUE_BACKEND=""

# ---------------------------------------------------------------------------
# conda 环境激活
# ---------------------------------------------------------------------------
activate_env() {
  # shellcheck disable=SC1091
  if command -v conda >/dev/null 2>&1; then
    source "$(conda info --base)/etc/profile.d/conda.sh"
    conda activate "$CONDA_ENV"
  elif [[ -f "$HOME/anaconda3/etc/profile.d/conda.sh" ]]; then
    source "$HOME/anaconda3/etc/profile.d/conda.sh"
    conda activate "$CONDA_ENV"
  else
    echo "⚠️  未找到 conda，假设当前 shell 已处于 $CONDA_ENV 环境" >&2
  fi
}

# ---------------------------------------------------------------------------
# 配置读取（单一事实来源：.env / src/common/config.py）
# ---------------------------------------------------------------------------
# 从 Python Config 读取启动参数，避免 shell 与 Python 各维护一套默认值而漂移。
# 幂等：仅在变量为空时读取一次。
load_config() {
  [[ -n "$API_HOST" && -n "$API_PORT" && -n "$REDIS_PORT" && -n "$QUEUE_BACKEND" ]] && return 0
  local out
  out="$(
    activate_env >/dev/null 2>&1
    python - <<'PY'
from urllib.parse import urlparse
from src.common.config import Config

c = Config()
redis_port = urlparse(c.REDIS_URL).port or 6379
print(f"{c.API_HOST}\t{c.API_PORT}\t{redis_port}\t{c.QUEUE_BACKEND}")
PY
  )" || { echo "✗ 读取配置失败（无法加载 src.common.config）" >&2; exit 1; }
  IFS=$'\t' read -r API_HOST API_PORT REDIS_PORT QUEUE_BACKEND <<<"$out"
}

# ---------------------------------------------------------------------------
# 进程工具
# ---------------------------------------------------------------------------
pid_file() { echo "$RUN_DIR/$1.pid"; }
log_file() { echo "$LOG_DIR/$1.log"; }

is_running() {
  local name="$1" pf
  pf="$(pid_file "$name")"
  [[ -f "$pf" ]] || return 1
  local pid
  pid="$(cat "$pf" 2>/dev/null || true)"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

# 探测 TCP 端口是否就绪（零依赖，避免依赖 redis-cli）。
# wait_port_ready <host> <port> [重试次数]
wait_port_ready() {
  local host="$1" port="$2" tries="${3:-20}" i
  for ((i = 0; i < tries; i++)); do
    if (exec 3<>"/dev/tcp/$host/$port") 2>/dev/null; then
      exec 3>&- 3<&-
      return 0
    fi
    sleep 0.3
  done
  return 1
}

# start_service <name> <command...>
start_service() {
  local name="$1"; shift
  if is_running "$name"; then
    echo "✓ $name 已在运行 (pid $(cat "$(pid_file "$name")"))"
    return 0
  fi
  local lf; lf="$(log_file "$name")"
  echo "→ 启动 $name ... (日志: ${lf#$PROJECT_ROOT/})"
  # 在子 shell 中激活环境后后台运行
  nohup bash -c "$(declare -f activate_env); activate_env; exec $*" \
    >>"$lf" 2>&1 &
  echo $! >"$(pid_file "$name")"
  sleep 1
  if is_running "$name"; then
    echo "✓ $name 启动成功 (pid $!)"
  else
    echo "✗ $name 启动失败，请查看日志: ${lf#$PROJECT_ROOT/}" >&2
    return 1
  fi
}

stop_service() {
  local name="$1" pf pid
  pf="$(pid_file "$name")"
  if ! is_running "$name"; then
    echo "· $name 未运行"
    rm -f "$pf"
    return 0
  fi
  pid="$(cat "$pf")"
  echo "→ 停止 $name (pid $pid) ..."
  kill "$pid" 2>/dev/null || true
  for _ in {1..10}; do
    kill -0 "$pid" 2>/dev/null || break
    sleep 0.5
  done
  if kill -0 "$pid" 2>/dev/null; then
    echo "  强制结束 $name"
    kill -9 "$pid" 2>/dev/null || true
  fi
  rm -f "$pf"
  echo "✓ $name 已停止"
}

# ---------------------------------------------------------------------------
# 各服务的启动命令
# ---------------------------------------------------------------------------
cmd_redis()  { echo "redis-server --port $REDIS_PORT --dir $RUN_DIR"; }
cmd_api()    { echo "python -m src.main api"; }
cmd_worker() { echo "python -m src.main worker"; }

start_one() {
  case "$1" in
    redis)
      # redis 常由系统/外部管理：若端口已在监听则视为就绪，跳过启动
      if wait_port_ready 127.0.0.1 "$REDIS_PORT" 1; then
        echo "✓ redis 已在监听 127.0.0.1:$REDIS_PORT（外部已启动），跳过"
        return 0
      fi
      start_service redis  "$(cmd_redis)"  ;;
    api)    start_service api     "$(cmd_api)"    ;;
    worker) start_service worker  "$(cmd_worker)" ;;
    *) echo "未知服务: $1" >&2; return 1 ;;
  esac
}

# ---------------------------------------------------------------------------
# 子命令
# ---------------------------------------------------------------------------
do_start() {
  load_config
  local target="${1:-all}"
  case "$target" in
    all)
      # fake 后端：任务在 API 进程内同步执行，无需 redis / worker
      if [[ "$QUEUE_BACKEND" == "fake" ]]; then
        echo "ℹ QUEUE_BACKEND=fake，仅启动 API（任务同步执行，无需 redis/worker）"
        start_one api
        return 0
      fi
      # redis 后端：先起 redis 并等待就绪，再起依赖它的 worker / api
      start_one redis
      echo "→ 等待 redis 就绪 (127.0.0.1:$REDIS_PORT) ..."
      if wait_port_ready 127.0.0.1 "$REDIS_PORT"; then
        echo "✓ redis 已就绪"
      else
        echo "✗ redis 未就绪，worker/api 可能连接失败，请查看日志" >&2
      fi
      start_one worker
      start_one api
      ;;
    worker)
      if [[ "$QUEUE_BACKEND" == "fake" ]]; then
        echo "⚠️  QUEUE_BACKEND=fake 下 worker 会立即退出（任务在 API 内同步执行）" >&2
      fi
      start_one worker
      ;;
    redis|api) start_one "$target" ;;
    *) echo "未知目标: $target" >&2; exit 1 ;;
  esac
}

do_stop() {
  local target="${1:-all}"
  case "$target" in
    all)
      stop_service api
      stop_service worker
      stop_redis
      ;;
    redis)  stop_redis ;;
    api|worker) stop_service "$target" ;;
    *) echo "未知目标: $target" >&2; exit 1 ;;
  esac
}

# 停止 redis：仅停由本脚本启动的实例；外部/系统管理的 redis 不动。
stop_redis() {
  if ! is_running redis; then
    load_config
    if wait_port_ready 127.0.0.1 "$REDIS_PORT" 1; then
      echo "· redis 由外部管理（端口 $REDIS_PORT 在监听），本脚本不停止它"
    else
      echo "· redis 未运行"
    fi
    rm -f "$(pid_file redis)"
    return 0
  fi
  stop_service redis
}

do_status() {
  load_config
  printf "%-8s %-10s %-8s %s\n" "服务" "状态" "PID" "端口/说明"
  printf "%-8s %-10s %-8s %s\n" "----" "----" "----" "--------"
  for name in redis worker api; do
    local extra="-"
    case "$name" in
      redis) extra="port $REDIS_PORT" ;;
      api)   extra="http://$API_HOST:$API_PORT" ;;
    esac
    # redis 可能由外部管理（无 pid 文件），用端口探测兜底
    if is_running "$name" || { [[ "$name" == "redis" ]] && wait_port_ready 127.0.0.1 "$REDIS_PORT" 1; }; then
      local pid="-"
      is_running "$name" && pid="$(cat "$(pid_file "$name")")"
      printf "%-8s \033[32m%-10s\033[0m %-8s %s\n" "$name" "running" "$pid" "$extra"
    else
      printf "%-8s \033[31m%-10s\033[0m %-8s %s\n" "$name" "stopped" "-" "$extra"
    fi
  done
}

do_logs() {
  local name="${1:-}"
  [[ -z "$name" ]] && { echo "用法: ./manage.sh logs [redis|api|worker]" >&2; exit 1; }
  local lf; lf="$(log_file "$name")"
  [[ -f "$lf" ]] || { echo "日志不存在: ${lf#$PROJECT_ROOT/}" >&2; exit 1; }
  tail -f "$lf"
}

do_run() {
  load_config
  local name="${1:-}"
  activate_env
  case "$name" in
    api)    echo "前台运行 API (Ctrl+C 退出)..."; exec $(cmd_api) ;;
    worker) echo "前台运行 Worker (Ctrl+C 退出)..."; exec $(cmd_worker) ;;
    redis)  echo "前台运行 Redis (Ctrl+C 退出)..."; exec $(cmd_redis) ;;
    *) echo "用法: ./manage.sh run [api|worker|redis]" >&2; exit 1 ;;
  esac
}

usage() {
  sed -n '3,23p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
case "${1:-}" in
  start)   shift; do_start "${1:-all}" ;;
  stop)    shift; do_stop  "${1:-all}" ;;
  restart) shift; do_stop "${1:-all}"; sleep 1; do_start "${1:-all}" ;;
  status)  do_status ;;
  logs)    shift; do_logs "${1:-}" ;;
  run)     shift; do_run  "${1:-}" ;;
  ""|-h|--help|help) usage ;;
  *) echo "未知命令: $1" >&2; usage; exit 1 ;;
esac
