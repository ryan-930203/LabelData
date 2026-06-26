# Web 标注平台

轻量本地 web 标注工具，用于浏览 `data.jsonl` 中的图片与对话，并按标签勾选保存标注结果。

## 数据格式

数据集文件夹需包含以下任一格式：

**JSONL 格式**（如 `80k_final_short/decoded`）

- `data.jsonl`（或 `decoded/data.jsonl`）
- `images/` 图片目录

**Parquet 格式**（如 `80k_short_cot_puzzle`）

- 文件夹内直接包含 `*.parquet` 文件
- 图片嵌入在 parquet 的 `image_buffer_list` 中，首次浏览时缓存到 `.label_cache/images/`

每条 jsonl 记录示例字段：`shard`、`row_index`、`conversations`、`image_id_list`、`images`。

标注 id 规则：`<shard去掉.parquet>::<row_index>`。

## 安装与启动

**推荐（跨平台）**：在项目根目录执行：

```bash
chmod +x start.sh
./start.sh
```

Linux 远程 / 端口转发部署：

```bash
OPEN_BROWSER=0 ./start.sh
# 或指定端口: PORT=8080 ./start.sh
```

**手动安装**：

```bash
cd app
python3 -m pip install -r requirements.txt
python3 app.py
```

若 `pip` 遇到 SSL 错误，可用清华 HTTP 镜像（跳过 SSL）：

```bash
pip install -i http://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn -r requirements.txt
```

浏览器打开：http://127.0.0.1:5000（若通过端口转发访问，使用转发后的地址即可）

启动时可指定默认数据集：

```bash
python app.py --folder /path/to/decoded
```

## 使用说明

1. 在页面顶部输入数据集文件夹绝对路径，点击「导入」；或点击「浏览」在本地目录中选择文件夹。
2. 左侧查看图片，中间查看 Human/GPT 对话，右侧勾选标签并填写备注。
3. 点击「保存」或 `Ctrl/Cmd+S` 保存当前条目标注（保存后自动跳下一条）。
4. 使用「上一条 / 下一条」或跳转 index 浏览数据。

## 标签配置

编辑 `app/labels.json`：

```json
{
  "labels": ["正确", "图文不符", "推理错误", "答案缺失", "需复核"]
}
```

刷新页面后标签会更新。

## 标注结果

标注保存在数据集文件夹内的 `annotations.json`（按 id 存储，支持断点续标）。

若该文件夹不可写，会回退到 `app/annotations_<hash>.json`。
