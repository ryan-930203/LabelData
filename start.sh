#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$ROOT_DIR/app"
VENV_DIR="$APP_DIR/.venv"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-5000}"
OPEN_BROWSER="${OPEN_BROWSER:-1}"

usage() {
  cat <<'EOF'
用法: ./start.sh [选项]

启动 Web 标注平台（Flask），默认地址 http://127.0.0.1:5000

选项（会传给 app.py）:
  --folder PATH   启动时默认导入的数据集文件夹
  --host HOST     监听地址（默认 127.0.0.1；Linux 远程访问可设 0.0.0.0）
  --port PORT     监听端口（默认 5000）
  -h, --help      显示帮助

环境变量:
  HOST            同 --host
  PORT            同 --port
  OPEN_BROWSER    设为 0 可禁止自动打开浏览器（默认 1）

示例:
  ./start.sh
  ./start.sh --folder ./80k_final_short/decoded
  ./start.sh --port 8080
  OPEN_BROWSER=0 HOST=0.0.0.0 ./start.sh
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

venv_python() {
  if [[ -x "$VENV_DIR/bin/python" ]]; then
    echo "$VENV_DIR/bin/python"
  elif [[ -x "$VENV_DIR/Scripts/python.exe" ]]; then
    echo "$VENV_DIR/Scripts/python.exe"
  else
    return 1
  fi
}

activate_venv() {
  if [[ -f "$VENV_DIR/bin/activate" ]]; then
    # shellcheck source=/dev/null
    source "$VENV_DIR/bin/activate"
  elif [[ -f "$VENV_DIR/Scripts/activate" ]]; then
    # shellcheck source=/dev/null
    source "$VENV_DIR/Scripts/activate"
  else
    echo "错误: 无法激活虚拟环境: $VENV_DIR" >&2
    exit 1
  fi
}

ensure_venv() {
  local py_bin

  if [[ -d "$VENV_DIR" ]]; then
    py_bin="$(venv_python || true)"
    if [[ -n "$py_bin" ]] && "$py_bin" -c "import sys; sys.exit(0)" >/dev/null 2>&1; then
      return 0
    fi
    echo "虚拟环境无效或来自其他平台，正在重建: $VENV_DIR"
    rm -rf "$VENV_DIR"
  fi

  echo "创建虚拟环境: $VENV_DIR"
  if ! python3 -m venv "$VENV_DIR" 2>/dev/null; then
    cat >&2 <<'EOF'
错误: 创建虚拟环境失败。
Linux 请先安装 venv 模块，例如:
  Debian/Ubuntu: sudo apt install python3-venv python3-pip
  RHEL/CentOS:   sudo dnf install python3
EOF
    exit 1
  fi
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

ensure_venv
activate_venv

echo "安装/检查依赖..."
python -m pip install -q -r "$APP_DIR/requirements.txt"

cd "$APP_DIR"

args=("$@")
if [[ ${#args[@]} -eq 0 ]]; then
  args=(--host "$HOST" --port "$PORT")
else
  has_host=0
  has_port=0
  for arg in "${args[@]}"; do
    [[ "$arg" == "--host" ]] && has_host=1
    [[ "$arg" == "--port" ]] && has_port=1
  done
  [[ "$has_host" -eq 0 ]] && args+=(--host "$HOST")
  [[ "$has_port" -eq 0 ]] && args+=(--port "$PORT")
fi

url="http://${HOST}:${PORT}"
if [[ "$OPEN_BROWSER" == "1" && "$HOST" =~ ^(127\.0\.0\.1|localhost)$ ]]; then
  (sleep 1 && open_browser "$url") &
fi

echo "启动服务: $url"
echo "按 Ctrl+C 停止"
exec python app.py "${args[@]}"
