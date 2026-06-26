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
  --host HOST     监听地址（默认 127.0.0.1）
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
  OPEN_BROWSER=0 ./start.sh
EOF
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

if [[ ! -d "$VENV_DIR" ]]; then
  echo "创建虚拟环境: $VENV_DIR"
  python3 -m venv "$VENV_DIR"
fi

# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"

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
  if command -v open >/dev/null 2>&1; then
    (sleep 1 && open "$url") &
  fi
fi

echo "启动服务: $url"
echo "按 Ctrl+C 停止"
exec python app.py "${args[@]}"
