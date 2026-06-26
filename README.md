# LabelData

Web 标注平台，支持 macOS / Linux / Windows（Git Bash/WSL）本地运行。

详细使用说明见 [app/README.md](app/README.md)。

## 快速启动

```bash
chmod +x start.sh
./start.sh
```

默认监听 `0.0.0.0:5000`，适合 SSH 端口转发或平台只暴露一个端口的场景：

```bash
# 服务器上
OPEN_BROWSER=0 ./start.sh

# 本地转发（示例）
ssh -L 8080:127.0.0.1:5000 user@server
# 浏览器打开 http://127.0.0.1:8080
```

若部署平台注入了 `PORT` 环境变量，脚本会自动使用该端口。

## Linux 依赖

```bash
# Debian / Ubuntu
sudo apt update
sudo apt install -y python3 python3-pip

# RHEL / CentOS / Fedora
sudo dnf install -y python3 python3-pip
```

首次运行 `./start.sh` 会用系统 Python 安装依赖并启动。若 pip 报权限错误，可先执行 `python3 -m pip install --user -r app/requirements.txt`。

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `HOST` | 监听地址 | `0.0.0.0` |
| `PORT` | 监听端口 | `5000`（部署平台注入时自动使用） |
| `OPEN_BROWSER` | 是否自动打开浏览器 | `1` |
| `DATA_FOLDER` | 启动时默认数据集路径 | 见 `app.py` |
| `PIP_INDEX_URL` | 自定义 pip 源 | 无（失败时自动尝试清华镜像） |
