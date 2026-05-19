#!/usr/bin/env bash

# 一键管理本地开发环境：同时启动或关闭 FastAPI 后端和 Vite 前端。
# 默认端口：
# - 后端：http://127.0.0.1:8000
# - 前端：http://127.0.0.1:5173

set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_PATH="${ROOT_DIR}/$(basename "${BASH_SOURCE[0]}")"
RUNTIME_DIR="${DEV_RUNTIME_DIR:-/tmp/test-wy-dev-${USER:-user}}"

BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
BACKEND_CONDA_ENV="${BACKEND_CONDA_ENV:-base}"

BACKEND_PID_FILE="${RUNTIME_DIR}/backend.pid"
FRONTEND_PID_FILE="${RUNTIME_DIR}/frontend.pid"
BACKEND_LOG_FILE="${RUNTIME_DIR}/backend.log"
FRONTEND_LOG_FILE="${RUNTIME_DIR}/frontend.log"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

ensure_runtime_dir() {
  mkdir -p "${RUNTIME_DIR}"
}

show_usage() {
  cat <<EOF
用法：
  ./dev.sh start     启动前端和后端
  ./dev.sh stop      关闭前端和后端
  ./dev.sh restart   重启前端和后端
  ./dev.sh status    查看运行状态
  ./dev.sh logs      查看日志路径

可选环境变量：
  BACKEND_CONDA_ENV  后端 conda 环境，默认：base
  BACKEND_PORT       后端端口，默认：8000
  FRONTEND_PORT      前端端口，默认：5173
EOF
}

read_pid() {
  local pid_file="$1"

  if [[ ! -f "${pid_file}" ]]; then
    return 1
  fi

  tr -d '[:space:]' < "${pid_file}"
}

is_running() {
  local pid_file="$1"
  local pid

  pid="$(read_pid "${pid_file}")" || return 1
  [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null
}

find_python() {
  if command -v python3 >/dev/null 2>&1; then
    command -v python3
  elif command -v python >/dev/null 2>&1; then
    command -v python
  else
    return 1
  fi
}

start_background_process() {
  local runner="$1"
  local log_file="$2"
  local pid_file="$3"
  local python_bin

  python_bin="$(find_python)" || {
    log "未找到 python 或 python3，无法启动后台进程。"
    return 1
  }

  # 使用 start_new_session 脱离当前命令会话，避免启动脚本退出时带走服务进程。
  "${python_bin}" - "${SCRIPT_PATH}" "${runner}" "${log_file}" "${pid_file}" <<'PY'
import subprocess
import sys
from pathlib import Path

script_path, runner, log_file, pid_file = sys.argv[1:5]

with open(log_file, "ab", buffering=0) as log:
    process = subprocess.Popen(
        ["bash", script_path, runner],
        stdout=log,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )

Path(pid_file).write_text(str(process.pid), encoding="utf-8")
PY
}

activate_conda_env() {
  # 非交互脚本中 conda 往往不是 shell 函数，所以先尝试加载常见 conda 初始化脚本。
  local conda_script=""
  local candidate
  local candidates=(
    "${HOME}/miniconda3/etc/profile.d/conda.sh"
    "${HOME}/anaconda3/etc/profile.d/conda.sh"
    "/opt/homebrew/Caskroom/miniconda/base/etc/profile.d/conda.sh"
    "/opt/anaconda3/etc/profile.d/conda.sh"
  )

  for candidate in "${candidates[@]}"; do
    if [[ -f "${candidate}" ]]; then
      conda_script="${candidate}"
      break
    fi
  done

  if [[ -n "${conda_script}" ]]; then
    # shellcheck disable=SC1090
    source "${conda_script}"
  elif command -v conda >/dev/null 2>&1; then
    eval "$(conda shell.bash hook)"
  else
    log "未找到 conda，请确认已经安装 conda 并配置到当前用户环境。"
    exit 1
  fi

  log "激活后端 conda 环境：${BACKEND_CONDA_ENV}"
  conda activate "${BACKEND_CONDA_ENV}" || exit 1
}

run_backend() {
  cd "${ROOT_DIR}/backend" || exit 1

  log "准备启动后端服务。"
  activate_conda_env

  # 使用 exec 让 PID 直接对应 uvicorn 进程，方便关闭脚本管理。
  exec python -m uvicorn app.main:app --reload --host "${BACKEND_HOST}" --port "${BACKEND_PORT}"
}

validate_frontend_ready() {
  if ! command -v npm >/dev/null 2>&1; then
    log "未找到 npm，请先安装 Node.js 和 npm。"
    return 1
  fi

  if [[ ! -d "${ROOT_DIR}/front/node_modules" ]]; then
    log "未找到 front/node_modules，请先执行：cd front && npm install"
    return 1
  fi
}

run_frontend() {
  cd "${ROOT_DIR}/front" || exit 1

  log "准备启动前端服务。"
  validate_frontend_ready || exit 1

  # 使用 npm 脚本启动 Vite，并显式传入端口，便于通过环境变量覆盖默认配置。
  exec npm run dev -- --host "${FRONTEND_HOST}" --port "${FRONTEND_PORT}"
}

start_service() {
  local name="$1"
  local runner="$2"
  local pid_file="$3"
  local log_file="$4"

  if is_running "${pid_file}"; then
    log "${name} 已在运行，PID：$(read_pid "${pid_file}")"
    return 0
  fi

  ensure_runtime_dir
  : > "${log_file}"

  log "正在启动${name}..."
  start_background_process "${runner}" "${log_file}" "${pid_file}" || return 1

  sleep 2
  if is_running "${pid_file}"; then
    log "${name} 启动成功，PID：$(read_pid "${pid_file}")，日志：${log_file}"
  else
    log "${name} 启动失败，最近日志如下："
    tail -n 40 "${log_file}" 2>/dev/null || true
    rm -f "${pid_file}"
    return 1
  fi
}

stop_process_tree() {
  local pid="$1"
  local child

  # 先递归关闭子进程，避免 Vite 或 uvicorn reload 子进程残留。
  for child in $(pgrep -P "${pid}" 2>/dev/null || true); do
    stop_process_tree "${child}"
  done

  kill "${pid}" 2>/dev/null || true
}

force_stop_process_tree() {
  local pid="$1"
  local child

  for child in $(pgrep -P "${pid}" 2>/dev/null || true); do
    force_stop_process_tree "${child}"
  done

  kill -9 "${pid}" 2>/dev/null || true
}

stop_service() {
  local name="$1"
  local pid_file="$2"
  local pid
  local attempt

  pid="$(read_pid "${pid_file}")" || {
    log "${name} 未运行。"
    return 0
  }

  if ! kill -0 "${pid}" 2>/dev/null; then
    log "${name} PID 文件已过期，正在清理。"
    rm -f "${pid_file}"
    return 0
  fi

  log "正在关闭${name}，PID：${pid}"
  stop_process_tree "${pid}"

  for attempt in {1..10}; do
    if ! kill -0 "${pid}" 2>/dev/null; then
      rm -f "${pid_file}"
      log "${name} 已关闭。"
      return 0
    fi
    sleep 1
  done

  log "${name} 未在预期时间内退出，执行强制关闭。"
  force_stop_process_tree "${pid}"
  rm -f "${pid_file}"
}

start_all() {
  local backend_was_running=0

  validate_frontend_ready || return 1

  if is_running "${BACKEND_PID_FILE}"; then
    backend_was_running=1
  fi

  start_service "后端" "__run_backend" "${BACKEND_PID_FILE}" "${BACKEND_LOG_FILE}" || return 1

  if ! start_service "前端" "__run_frontend" "${FRONTEND_PID_FILE}" "${FRONTEND_LOG_FILE}"; then
    if [[ "${backend_was_running}" -eq 0 ]]; then
      log "前端启动失败，正在关闭本次启动的后端。"
      stop_service "后端" "${BACKEND_PID_FILE}"
    fi
    return 1
  fi

  log "本地开发环境已启动。"
  log "后端地址：http://${BACKEND_HOST}:${BACKEND_PORT}"
  log "前端地址：http://${FRONTEND_HOST}:${FRONTEND_PORT}"
}

stop_all() {
  # 先关闭前端，再关闭后端，符合本地开发时的依赖方向。
  stop_service "前端" "${FRONTEND_PID_FILE}"
  stop_service "后端" "${BACKEND_PID_FILE}"
}

show_status() {
  if is_running "${BACKEND_PID_FILE}"; then
    log "后端运行中，PID：$(read_pid "${BACKEND_PID_FILE}")，地址：http://${BACKEND_HOST}:${BACKEND_PORT}"
  else
    log "后端未运行。"
  fi

  if is_running "${FRONTEND_PID_FILE}"; then
    log "前端运行中，PID：$(read_pid "${FRONTEND_PID_FILE}")，地址：http://${FRONTEND_HOST}:${FRONTEND_PORT}"
  else
    log "前端未运行。"
  fi
}

show_logs() {
  ensure_runtime_dir
  log "后端日志：${BACKEND_LOG_FILE}"
  log "前端日志：${FRONTEND_LOG_FILE}"
}

case "${1:-}" in
  __run_backend)
    run_backend
    ;;
  __run_frontend)
    run_frontend
    ;;
  start)
    start_all
    ;;
  stop)
    stop_all
    ;;
  restart)
    stop_all
    start_all
    ;;
  status)
    show_status
    ;;
  logs)
    show_logs
    ;;
  -h|--help|help|"")
    show_usage
    ;;
  *)
    log "未知命令：$1"
    show_usage
    exit 1
    ;;
esac
