# LabelData

Web 标注平台，支持 macOS / Linux / Windows（Git Bash/WSL）本地运行。

详细使用说明见 [app/README.md](app/README.md)。

## 快速启动

```bash
chmod +x start.sh
./start.sh
```

Linux 远程服务器（允许局域网/外网访问）：

```bash
OPEN_BROWSER=0 HOST=0.0.0.0 ./start.sh
```

## Linux 依赖

```bash
# Debian / Ubuntu
sudo apt update
sudo apt install -y python3 python3-venv python3-pip

# RHEL / CentOS / Fedora
sudo dnf install -y python3 python3-pip
```

首次运行 `./start.sh` 会自动创建虚拟环境并安装依赖。若本地存在其他平台创建的 `.venv`，脚本会自动检测并重建。

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `HOST` | 监听地址 | `127.0.0.1` |
| `PORT` | 监听端口 | `5000` |
| `OPEN_BROWSER` | 是否自动打开浏览器 | `1` |
| `DATA_FOLDER` | 启动时默认数据集路径 | 见 `app.py` |
