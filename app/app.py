from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import pyarrow.parquet as pq
from flask import Flask, jsonify, request, send_from_directory

APP_DIR = Path(__file__).resolve().parent
LABELS_PATH = APP_DIR / "labels.json"

app = Flask(__name__, static_folder="static", static_url_path="/static")

NO_CACHE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}


@app.after_request
def disable_proxy_cache(response):
    if request.path == "/" or request.path.startswith("/api/"):
        response.headers.update(NO_CACHE_HEADERS)
    return response


class DatasetState:
    def __init__(self):
        self.folder: Path | None = None
        self.source_type: str | None = None  # "jsonl" | "parquet"
        self.jsonl_path: Path | None = None
        self.images_dir: Path | None = None
        self.image_cache_dir: Path | None = None
        self.annotations_path: Path | None = None
        self.offsets: list[int] = []
        self.parquet_refs: list[tuple[Path, int]] = []
        self.ids: list[str] = []
        self.annotations: dict = {}
        self._parquet_table_cache: dict[str, object] = {}

    def clear(self):
        self.folder = None
        self.source_type = None
        self.jsonl_path = None
        self.images_dir = None
        self.image_cache_dir = None
        self.annotations_path = None
        self.offsets = []
        self.parquet_refs = []
        self.ids = []
        self.annotations = {}
        self._parquet_table_cache = {}

    @property
    def total(self) -> int:
        return len(self.ids)

    @property
    def annotated_count(self) -> int:
        return len(self.annotations)


current = DatasetState()

SHARD_RE = re.compile(r'"shard"\s*:\s*"([^"]+)"')
ROW_INDEX_RE = re.compile(r'"row_index"\s*:\s*(\d+)')


def make_item_id(shard: str, row_index: int) -> str:
    shard_key = shard.replace(".parquet", "")
    return f"{shard_key}::{row_index}"


def detect_image_ext(data: bytes) -> str:
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:4] == b"\x89PNG":
        return ".png"
    if data[:4] == b"GIF8":
        return ".gif"
    if data[:4] == b"RIFF" and len(data) > 12 and data[8:12] == b"WEBP":
        return ".webp"
    return ".png"


def resolve_jsonl_dataset(folder: Path) -> tuple[Path, Path]:
    candidates = [
        folder / "data.jsonl",
        folder / "decoded" / "data.jsonl",
    ]
    jsonl_path = next((p for p in candidates if p.is_file()), None)
    if jsonl_path is None:
        raise ValueError("未找到 data.jsonl")

    images_candidates = [
        jsonl_path.parent / "images",
        folder / "images",
        folder / "decoded" / "images",
    ]
    images_dir = next((p for p in images_candidates if p.is_dir()), None)
    if images_dir is None:
        raise ValueError("未找到 images 目录")

    return jsonl_path, images_dir


def resolve_parquet_dataset(folder: Path) -> list[Path]:
    files = sorted(folder.glob("*.parquet"))
    if not files:
        raise ValueError("未找到 parquet 文件")
    return files


def annotations_fallback_path(folder: Path) -> Path:
    digest = hashlib.sha256(str(folder.resolve()).encode()).hexdigest()[:16]
    return APP_DIR / f"annotations_{digest}.json"


def resolve_annotations_path(folder: Path) -> Path:
    primary = folder / "annotations.json"
    try:
        if primary.exists():
            return primary
        primary.touch()
        primary.unlink()
        return primary
    except OSError:
        return annotations_fallback_path(folder)


def load_annotations(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_annotations(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def load_labels() -> list[str]:
    if not LABELS_PATH.exists():
        return []
    with open(LABELS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    labels = data.get("labels", [])
    return labels if isinstance(labels, list) else []


def index_jsonl(jsonl_path: Path) -> tuple[list[int], list[str]]:
    offsets: list[int] = []
    ids: list[str] = []
    with open(jsonl_path, "rb") as f:
        while True:
            offset = f.tell()
            line = f.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            offsets.append(offset)
            text = line.decode("utf-8")
            shard_m = SHARD_RE.search(text)
            row_m = ROW_INDEX_RE.search(text)
            shard = shard_m.group(1) if shard_m else "unknown"
            row_index = int(row_m.group(1)) if row_m else len(ids)
            ids.append(make_item_id(shard, row_index))
    return offsets, ids


def index_parquet_files(parquet_files: list[Path]) -> tuple[list[tuple[Path, int]], list[str]]:
    refs: list[tuple[Path, int]] = []
    ids: list[str] = []
    for file_path in parquet_files:
        num_rows = pq.read_metadata(file_path).num_rows
        stem = file_path.stem
        for row_idx in range(num_rows):
            refs.append((file_path, row_idx))
            ids.append(make_item_id(stem, row_idx))
    return refs, ids


def read_jsonl_record(index: int) -> dict:
    with open(current.jsonl_path, "rb") as f:
        f.seek(current.offsets[index])
        line = f.readline()
    return json.loads(line)


def load_parquet_table(file_path: Path):
    key = str(file_path)
    if key not in current._parquet_table_cache:
        current._parquet_table_cache.clear()
        current._parquet_table_cache[key] = pq.read_table(
            file_path,
            columns=["clean_content", "image_buffer_list", "source"],
        )
    return current._parquet_table_cache[key]


def read_parquet_record(index: int) -> dict:
    file_path, row_idx = current.parquet_refs[index]
    table = load_parquet_table(file_path)
    row = table.slice(row_idx, 1).to_pydict()

    clean_content = json.loads(row["clean_content"][0])
    conversations = json.loads(clean_content["text"])
    image_buffer_list = row["image_buffer_list"][0] or []
    source = row["source"][0] if row.get("source") else ""

    image_id_list = clean_content.get("image_id_list") or []
    if not image_id_list and image_buffer_list:
        image_id_list = [img["image_id"] for img in image_buffer_list]

    cache_parquet_images(image_buffer_list)

    return {
        "source": source,
        "shard": file_path.name,
        "row_index": row_idx,
        "task_type": clean_content.get("task_type"),
        "image_id_list": image_id_list,
        "conversations": conversations,
    }


def cache_parquet_images(image_buffer_list: list) -> None:
    if current.image_cache_dir is None:
        return
    current.image_cache_dir.mkdir(parents=True, exist_ok=True)
    for img in image_buffer_list:
        img_id = img.get("image_id")
        buffer = img.get("buffer")
        if not img_id or not buffer:
            continue
        if isinstance(buffer, memoryview):
            buffer = buffer.tobytes()
        ext = detect_image_ext(buffer)
        cache_path = current.image_cache_dir / f"{img_id}{ext}"
        if not cache_path.exists():
            cache_path.write_bytes(buffer)


def read_record_at(index: int) -> dict:
    if index < 0 or index >= current.total:
        raise IndexError("index out of range")
    if current.source_type == "jsonl":
        return read_jsonl_record(index)
    return read_parquet_record(index)


def parse_conversations(record: dict) -> tuple[str, str]:
    human_text = ""
    gpt_text = ""
    for conv in record.get("conversations", []):
        role = conv.get("from", "")
        value = conv.get("value", "")
        if role == "human":
            human_text = value
        elif role == "gpt":
            gpt_text = value
    return human_text, gpt_text


def find_image_file(image_id: str) -> Path | None:
    search_dirs: list[Path] = []
    if current.images_dir is not None:
        search_dirs.append(current.images_dir)
    if current.image_cache_dir is not None:
        search_dirs.append(current.image_cache_dir)

    for directory in search_dirs:
        for ext in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
            candidate = directory / f"{image_id}{ext}"
            if candidate.is_file():
                return candidate
    return None


def open_dataset(folder_str: str) -> dict:
    folder = Path(folder_str).expanduser().resolve()
    if not folder.is_dir():
        raise ValueError(f"路径不是文件夹: {folder}")

    current.clear()

    annotations_path = resolve_annotations_path(folder)
    annotations = load_annotations(annotations_path)

    try:
        jsonl_path, images_dir = resolve_jsonl_dataset(folder)
        offsets, ids = index_jsonl(jsonl_path)
        if not offsets:
            raise ValueError("data.jsonl 为空")

        current.folder = folder
        current.source_type = "jsonl"
        current.jsonl_path = jsonl_path
        current.images_dir = images_dir
        current.offsets = offsets
        current.ids = ids
    except ValueError as jsonl_err:
        try:
            parquet_files = resolve_parquet_dataset(folder)
            refs, ids = index_parquet_files(parquet_files)
            if not refs:
                raise ValueError("parquet 文件为空")

            current.folder = folder
            current.source_type = "parquet"
            current.parquet_refs = refs
            current.ids = ids
            current.image_cache_dir = folder / ".label_cache" / "images"
        except ValueError as parquet_err:
            raise ValueError(
                f"未找到可识别的数据格式。jsonl: {jsonl_err}; parquet: {parquet_err}"
            )

    current.annotations_path = annotations_path
    current.annotations = annotations

    return dataset_info()


def folder_dataset_hint(folder: Path) -> str | None:
    try:
        resolve_jsonl_dataset(folder)
        return "jsonl"
    except ValueError:
        pass
    try:
        if any(folder.glob("*.parquet")):
            return "parquet"
    except OSError:
        pass
    return None


def resolve_browse_path(path_str: str | None) -> Path:
    if not path_str:
        workspace = APP_DIR.parent
        if workspace.is_dir():
            return workspace.resolve()
        return Path.home().resolve()

    path = Path(path_str).expanduser().resolve()
    if not path.exists():
        raise ValueError(f"路径不存在: {path_str}")
    if not path.is_dir():
        raise ValueError(f"不是文件夹: {path_str}")
    return path


def browse_directory(path_str: str | None) -> dict:
    current_path = resolve_browse_path(path_str)
    parent = current_path.parent
    parent_path = str(parent) if parent != current_path else None

    entries = []
    try:
        children = sorted(current_path.iterdir(), key=lambda p: p.name.lower())
    except OSError as e:
        raise ValueError(f"无法读取目录: {e}")

    for child in children:
        if not child.is_dir():
            continue
        if child.name.startswith(".") and child.name != ".label_cache":
            continue
        try:
            entries.append(
                {
                    "name": child.name,
                    "path": str(child.resolve()),
                    "dataset_type": folder_dataset_hint(child),
                }
            )
        except OSError:
            continue

    return {
        "path": str(current_path),
        "parent": parent_path,
        "workspace": str(APP_DIR.parent.resolve()),
        "home": str(Path.home().resolve()),
        "dataset_type": folder_dataset_hint(current_path),
        "entries": entries,
    }


def dataset_info() -> dict:
    info = {
        "folder": str(current.folder),
        "source_type": current.source_type,
        "annotations_path": str(current.annotations_path),
        "total": current.total,
        "annotated_count": current.annotated_count,
    }
    if current.source_type == "jsonl":
        info["jsonl_path"] = str(current.jsonl_path)
        info["images_dir"] = str(current.images_dir)
    else:
        info["parquet_files"] = len({ref[0] for ref in current.parquet_refs})
        info["image_cache_dir"] = str(current.image_cache_dir)
    return info


@app.route("/")
def index_page():
    response = send_from_directory(app.static_folder, "index.html", conditional=False)
    response.headers.update(NO_CACHE_HEADERS)
    return response


@app.route("/api/browse")
def api_browse():
    path_arg = request.args.get("path", "").strip() or None
    try:
        return jsonify(browse_directory(path_arg))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/open", methods=["POST"])
def api_open():
    body = request.get_json(silent=True) or {}
    folder = body.get("folder", "").strip()
    if not folder:
        return jsonify({"error": "请提供 folder 路径"}), 400
    try:
        info = open_dataset(folder)
        return jsonify({"ok": True, **info})
    except (ValueError, OSError, json.JSONDecodeError) as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/meta")
def api_meta():
    labels = load_labels()
    if current.folder is None:
        return jsonify(
            {
                "loaded": False,
                "labels": labels,
                "folder": None,
                "total": 0,
                "annotated_count": 0,
            }
        )
    return jsonify({"loaded": True, "labels": labels, **dataset_info()})


@app.route("/api/item")
def api_item():
    if current.folder is None:
        return jsonify({"error": "请先导入数据集文件夹"}), 400

    index = request.args.get("index", type=int)
    if index is None:
        return jsonify({"error": "请提供 index 参数"}), 400
    if index < 0 or index >= current.total:
        return jsonify({"error": f"index 超出范围 (0-{current.total - 1})"}), 400

    record = read_record_at(index)
    item_id = current.ids[index]
    human_text, gpt_text = parse_conversations(record)
    image_id_list = record.get("image_id_list", [])

    images = []
    for img_id in image_id_list:
        img_file = find_image_file(img_id)
        images.append({"image_id": img_id, "available": img_file is not None})

    annotation = current.annotations.get(item_id, {})

    return jsonify(
        {
            "index": index,
            "id": item_id,
            "source": record.get("source"),
            "shard": record.get("shard"),
            "row_index": record.get("row_index"),
            "task_type": record.get("task_type"),
            "image_id_list": image_id_list,
            "images": images,
            "human": human_text,
            "gpt": gpt_text,
            "annotation": {
                "labels": annotation.get("labels", []),
                "note": annotation.get("note", ""),
                "updated_at": annotation.get("updated_at"),
            },
        }
    )


@app.route("/api/image/<image_id>")
def api_image(image_id: str):
    if current.folder is None:
        return jsonify({"error": "请先导入数据集文件夹"}), 400

    img_file = find_image_file(image_id)
    if img_file is None:
        return jsonify({"error": f"图片不存在: {image_id}"}), 404

    return send_from_directory(img_file.parent, img_file.name)


@app.route("/api/annotate", methods=["POST"])
def api_annotate():
    if current.folder is None:
        return jsonify({"error": "请先导入数据集文件夹"}), 400

    body = request.get_json(silent=True) or {}
    item_id = body.get("id")
    index = body.get("index")
    labels = body.get("labels", [])
    note = body.get("note", "")

    if not item_id:
        return jsonify({"error": "请提供 id"}), 400
    if index is None or index < 0 or index >= current.total:
        return jsonify({"error": "index 无效"}), 400
    if current.ids[index] != item_id:
        return jsonify({"error": "id 与 index 不匹配"}), 400
    if not isinstance(labels, list):
        return jsonify({"error": "labels 必须是数组"}), 400

    allowed = set(load_labels())
    clean_labels = [label for label in labels if isinstance(label, str) and label in allowed]

    current.annotations[item_id] = {
        "index": index,
        "labels": clean_labels,
        "note": note if isinstance(note, str) else "",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    save_annotations(current.annotations_path, current.annotations)

    return jsonify(
        {
            "ok": True,
            "id": item_id,
            "annotated_count": current.annotated_count,
            "annotation": current.annotations[item_id],
        }
    )


@app.route("/api/export")
def api_export():
    if current.folder is None:
        return jsonify({"error": "请先导入数据集文件夹"}), 400
    return jsonify(
        {
            "folder": str(current.folder),
            "annotations_path": str(current.annotations_path),
            "annotations": current.annotations,
        }
    )


def main():
    parser = argparse.ArgumentParser(description="Web 标注平台")
    parser.add_argument(
        "--folder",
        default=os.environ.get(
            "DATA_FOLDER",
            str((APP_DIR.parent / "80k_final_short" / "decoded").resolve()),
        ),
        help="启动时默认导入的数据集文件夹路径（也可通过环境变量 DATA_FOLDER 设置）",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("HOST", "0.0.0.0"),
        help="监听地址（默认 0.0.0.0，便于端口转发/远程访问）",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PORT", "5000")),
        help="监听端口（默认 5000，也可通过环境变量 PORT 设置）",
    )
    args = parser.parse_args()

    if args.folder and Path(args.folder).expanduser().exists():
        try:
            info = open_dataset(args.folder)
            print(
                f"已导入数据集 [{info['source_type']}]: {info['folder']} ({info['total']} 条)"
            )
        except Exception as e:
            print(f"默认数据集导入失败: {e}")

    print(f"监听 {args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
