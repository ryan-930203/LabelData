#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$ROOT_DIR/app"
HOST="${HOST:-0.0.0.0}"
PORT_EXPLICIT=0
[[ -n "${PORT:-}" ]] && PORT_EXPLICIT=1
PORT="${PORT:-5000}"
OPEN_BROWSER="${OPEN_BROWSER:-1}"

usage() {
  cat <<'EOF'
用法: ./start.sh [选项]

启动 Web 标注平台（Flask），默认监听 0.0.0.0:5000（适配端口转发部署）

选项（会传给 app.py）:
  --folder PATH   启动时默认导入的数据集文件夹
  --host HOST     监听地址（默认 0.0.0.0）
  --port PORT     监听端口（默认 5000，或环境变量 PORT）
  -h, --help      显示帮助

环境变量:
  HOST            同 --host
  PORT            同 --port（端口转发平台通常会注入此变量）
  OPEN_BROWSER    设为 0 可禁止自动打开浏览器（默认 1）

示例:
  ./start.sh
  ./start.sh --folder ./80k_final_short/decoded
  PORT=8080 ./start.sh
  OPEN_BROWSER=0 ./start.sh
EOF
}

open_browser() {
  local url="$1"
  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$url" >/dev/null 2>&1 &
  elif command -v open >/dev/null 2>&1; then
    open "$url" >/dev/null 2>&1 &
  elif [[ -n "${WINDIR:-}" ]] && command -v cmd.exe >/dev/null 2>&1; then
    cmd.exe /c start "" "$url" >/dev/null 2>&1 &
  fi
}

deps_ready() {
  python3 -c "import flask, pyarrow" >/dev/null 2>&1
}

install_deps() {
  if deps_ready; then
    echo "依赖已就绪，跳过安装"
    return 0
  fi

  echo "安装/检查依赖..."
  local req_file="$APP_DIR/requirements.txt"
  local -a pip_args=(-q -r "$req_file")

  if [[ -n "${PIP_INDEX_URL:-}" ]]; then
    pip_args=(-q -i "$PIP_INDEX_URL" -r "$req_file")
    if [[ -n "${PIP_TRUSTED_HOST:-}" ]]; then
      pip_args+=(--trusted-host "$PIP_TRUSTED_HOST")
    fi
    if python3 -m pip install "${pip_args[@]}"; then
      return 0
    fi
  elif python3 -m pip install --retries 1 --timeout 30 "${pip_args[@]}"; then
    return 0
  fi

  echo "默认 PyPI 安装失败，尝试清华镜像..." >&2
  python3 -m pip install -q \
    -i http://pypi.tuna.tsinghua.edu.cn/simple \
    --trusted-host pypi.tuna.tsinghua.edu.cn \
    -r "$req_file"

  if ! deps_ready; then
    echo "错误: 依赖安装失败，请检查网络或手动执行:" >&2
    echo "  python3 -m pip install -i http://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn -r app/requirements.txt" >&2
    exit 1
  fi
}

port_available() {
  python3 - "$1" "$2" <<'PY'
import socket
import sys

host = sys.argv[1]
port = int(sys.argv[2])
bind_host = "" if host in ("0.0.0.0", "::") else host
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
try:
    sock.bind((bind_host, port))
except OSError:
    sys.exit(1)
finally:
    sock.close()
PY
}

resolve_port() {
  local host="$1"
  local preferred="$2"
  local strict="$3"
  local port="$preferred"
  local i

  if port_available "$host" "$port"; then
    echo "$port"
    return 0
  fi

  if [[ "$strict" == "1" ]]; then
    echo "错误: 端口 ${port} 已被占用。" >&2
    if [[ "$port" == "5000" ]] && [[ "$(uname -s)" == "Darwin" ]]; then
      echo "macOS 上常见原因是 AirPlay 接收器占用了 5000，可关闭「系统设置 → 通用 → AirDrop 与隔空播放 → 隔空播放接收器」，或使用 PORT=5050 ./start.sh" >&2
    fi
    exit 1
  fi

  for ((i = 1; i <= 20; i++)); do
    port=$((preferred + i))
    if port_available "$host" "$port"; then
      echo "警告: 端口 ${preferred} 已被占用，改用 ${port}" >&2
      echo "$port"
      return 0
    fi
  done

  echo "错误: 端口 ${preferred}-$((preferred + 20)) 均被占用" >&2
  exit 1
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "错误: 未找到 python3，请先安装 Python 3。" >&2
  exit 1
fi

if [[ ! -d "$APP_DIR" ]]; then
  echo "错误: 未找到 app 目录: $APP_DIR" >&2
  exit 1
fi

install_deps

cd "$APP_DIR"

args=("$@")
REQUESTED_PORT="$PORT"
PORT_STRICT="$PORT_EXPLICIT"

for ((i = 0; i < ${#args[@]}; i++)); do
  if [[ "${args[i]}" == "--port" && -n "${args[i + 1]:-}" ]]; then
    REQUESTED_PORT="${args[i + 1]}"
    PORT_STRICT=1
    break
  fi
done

PORT="$(resolve_port "$HOST" "$REQUESTED_PORT" "$PORT_STRICT")"

if [[ ${#args[@]} -eq 0 ]]; then
  args=(--host "$HOST" --port "$PORT")
else
  has_host=0
  has_port=0
  new_args=()
  i=0
  while (( i < ${#args[@]} )); do
    case "${args[i]}" in
      --host)
        has_host=1
        new_args+=(--host "$HOST")
        ((i += 2))
        ;;
      --port)
        has_port=1
        new_args+=(--port "$PORT")
        ((i += 2))
        ;;
      *)
        new_args+=("${args[i]}")
        ((i += 1))
        ;;
    esac
  done
  [[ "$has_host" -eq 0 ]] && new_args=(--host "$HOST" "${new_args[@]}")
  [[ "$has_port" -eq 0 ]] && new_args+=(--port "$PORT")
  args=("${new_args[@]}")
fi

if [[ "$OPEN_BROWSER" == "1" ]]; then
  (sleep 1 && open_browser "http://127.0.0.1:${PORT}") &
fi

echo "监听 ${HOST}:${PORT}"
echo "本机访问: http://127.0.0.1:${PORT}"
echo "端口转发后，在浏览器打开转发地址即可（前端 API 使用相对路径，无需额外配置）"
echo "按 Ctrl+C 停止"
exec python3 app.py "${args[@]}"
