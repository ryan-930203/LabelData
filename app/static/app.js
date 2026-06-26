const state = {
  loaded: false,
  total: 0,
  annotatedCount: 0,
  currentIndex: 0,
  labels: [],
  currentItem: null,
};

const els = {
  folderInput: document.getElementById("folder-input"),
  btnBrowse: document.getElementById("btn-browse"),
  btnOpen: document.getElementById("btn-open"),
  folderStatus: document.getElementById("folder-status"),
  btnPrev: document.getElementById("btn-prev"),
  btnNext: document.getElementById("btn-next"),
  progressText: document.getElementById("progress-text"),
  annotatedText: document.getElementById("annotated-text"),
  jumpInput: document.getElementById("jump-input"),
  btnJump: document.getElementById("btn-jump"),
  btnRandom: document.getElementById("btn-random"),
  btnSave: document.getElementById("btn-save"),
  workspace: document.getElementById("workspace"),
  emptyState: document.getElementById("empty-state"),
  imagesContainer: document.getElementById("images-container"),
  itemMeta: document.getElementById("item-meta"),
  humanText: document.getElementById("human-text"),
  gptText: document.getElementById("gpt-text"),
  labelsContainer: document.getElementById("labels-container"),
  noteInput: document.getElementById("note-input"),
  lightbox: document.getElementById("lightbox"),
  lightboxImg: document.getElementById("lightbox-img"),
  toast: document.getElementById("toast"),
  browseModal: document.getElementById("browse-modal"),
  btnBrowseClose: document.getElementById("btn-browse-close"),
  btnBrowseUp: document.getElementById("btn-browse-up"),
  btnBrowseHome: document.getElementById("btn-browse-home"),
  btnBrowseWorkspace: document.getElementById("btn-browse-workspace"),
  browseCurrentPath: document.getElementById("browse-current-path"),
  browseDatasetHint: document.getElementById("browse-dataset-hint"),
  browseList: document.getElementById("browse-list"),
  btnBrowseSelect: document.getElementById("btn-browse-select"),
  btnBrowseImport: document.getElementById("btn-browse-import"),
};

const browseState = {
  path: null,
  home: null,
  workspace: null,
};

function showToast(message) {
  els.toast.textContent = message;
  els.toast.classList.remove("hidden");
  clearTimeout(showToast._timer);
  showToast._timer = setTimeout(() => els.toast.classList.add("hidden"), 2200);
}

async function api(path, options = {}) {
  const res = await fetch(path, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.error || `请求失败 (${res.status})`);
  }
  return data;
}

function setNavEnabled(enabled) {
  els.btnPrev.disabled = !enabled;
  els.btnNext.disabled = !enabled;
  els.jumpInput.disabled = !enabled;
  els.btnJump.disabled = !enabled;
  els.btnRandom.disabled = !enabled;
  els.btnSave.disabled = !enabled;
}

function updateProgress() {
  els.progressText.textContent = state.loaded
    ? `${state.currentIndex + 1} / ${state.total}`
    : "0 / 0";
  els.annotatedText.textContent = `已标注 ${state.annotatedCount}`;
  els.jumpInput.value = state.currentIndex;
  els.jumpInput.max = Math.max(0, state.total - 1);
}

function renderLabels() {
  els.labelsContainer.innerHTML = "";
  state.labels.forEach((label) => {
    const wrapper = document.createElement("label");
    wrapper.className = "label-option";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.value = label;
    input.dataset.label = label;
    const span = document.createElement("span");
    span.textContent = label;
    wrapper.appendChild(input);
    wrapper.appendChild(span);
    els.labelsContainer.appendChild(wrapper);
  });
}

function formatConversationText(text, imageIdList) {
  if (!text) return "";
  const idToIndex = new Map(imageIdList.map((id, idx) => [id, idx + 1]));
  const escaped = text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  return escaped.replace(/&lt;image&gt;([a-f0-9]+)&lt;\/image&gt;/g, (_, imageId) => {
    const idx = idToIndex.get(imageId);
    const label = idx ? `图${idx}` : "图";
    return `<span class="image-tag">${label}</span>`;
  });
}

function renderImages(item) {
  els.imagesContainer.innerHTML = "";
  item.images.forEach((img, idx) => {
    const card = document.createElement("div");
    card.className = "image-card";
    if (img.available) {
      const imageEl = document.createElement("img");
      imageEl.src = `/api/image/${img.image_id}?t=${Date.now()}`;
      imageEl.alt = `image ${idx + 1}`;
      imageEl.addEventListener("click", () => {
        els.lightboxImg.src = imageEl.src;
        els.lightbox.classList.remove("hidden");
      });
      card.appendChild(imageEl);
    } else {
      const missing = document.createElement("div");
      missing.className = "image-missing";
      missing.textContent = `图片缺失: ${img.image_id}`;
      card.appendChild(missing);
    }
    const idEl = document.createElement("div");
    idEl.className = "image-id";
    idEl.textContent = `图${idx + 1}: ${img.image_id}`;
    card.appendChild(idEl);
    els.imagesContainer.appendChild(card);
  });
}

function applyAnnotation(annotation) {
  const selected = new Set(annotation?.labels || []);
  els.labelsContainer.querySelectorAll("input[type=checkbox]").forEach((input) => {
    input.checked = selected.has(input.value);
  });
  els.noteInput.value = annotation?.note || "";
}

function jumpToRandom() {
  if (!state.loaded || state.total <= 0) return;
  let idx;
  if (state.total === 1) {
    idx = 0;
  } else {
    do {
      idx = Math.floor(Math.random() * state.total);
    } while (idx === state.currentIndex);
  }
  loadItem(idx);
}

async function loadItem(index) {
  if (!state.loaded) return;
  const item = await api(`/api/item?index=${index}`);
  state.currentIndex = item.index;
  state.currentItem = item;
  updateProgress();

  els.itemMeta.textContent = [
    `ID: ${item.id}`,
    `task: ${item.task_type || "-"}`,
    `shard: ${item.shard || "-"}`,
    `row_index: ${item.row_index ?? "-"}`,
  ].join(" | ");

  els.humanText.innerHTML = formatConversationText(item.human, item.image_id_list);
  els.gptText.innerHTML = formatConversationText(item.gpt, item.image_id_list);
  renderImages(item);
  applyAnnotation(item.annotation);
}

function datasetTypeLabel(type) {
  if (type === "jsonl") return "JSONL";
  if (type === "parquet") return "Parquet";
  return "";
}

function closeBrowseModal() {
  els.browseModal.classList.add("hidden");
}

async function loadBrowseDirectory(path) {
  const query = path ? `?path=${encodeURIComponent(path)}` : "";
  const data = await api(`/api/browse${query}`);
  browseState.path = data.path;
  browseState.home = data.home;
  browseState.workspace = data.workspace;
  els.browseCurrentPath.textContent = data.path;
  els.btnBrowseUp.disabled = !data.parent;
  browseState.parent = data.parent;

  const hint = data.dataset_type
    ? `当前文件夹可识别为 ${datasetTypeLabel(data.dataset_type)} 数据集`
    : "当前文件夹未检测到 jsonl/parquet 数据集格式";
  els.browseDatasetHint.textContent = hint;

  els.browseList.innerHTML = "";
  if (!data.entries.length) {
    const empty = document.createElement("li");
    empty.className = "browse-item muted";
    empty.textContent = "没有子文件夹";
    els.browseList.appendChild(empty);
    return;
  }

  data.entries.forEach((entry) => {
    const li = document.createElement("li");
    li.className = "browse-item";
    const name = document.createElement("span");
    name.className = "browse-item-name";
    name.textContent = entry.name;
    li.appendChild(name);
    if (entry.dataset_type) {
      const badge = document.createElement("span");
      badge.className = "browse-badge";
      badge.textContent = datasetTypeLabel(entry.dataset_type);
      li.appendChild(badge);
    }
    li.addEventListener("click", () => loadBrowseDirectory(entry.path));
    els.browseList.appendChild(li);
  });
}

async function openBrowseModal() {
  els.browseModal.classList.remove("hidden");
  try {
    await loadBrowseDirectory(els.folderInput.value.trim() || null);
  } catch (err) {
    showToast(err.message);
  }
}

function selectBrowseFolder(importAfterSelect = false) {
  if (!browseState.path) return;
  els.folderInput.value = browseState.path;
  closeBrowseModal();
  if (importAfterSelect) {
    openFolder();
  } else {
    showToast("已选择文件夹");
  }
}

async function openFolder() {
  const folder = els.folderInput.value.trim();
  if (!folder) {
    showToast("请输入文件夹路径");
    return;
  }
  try {
    const data = await api("/api/open", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ folder }),
    });
    state.loaded = true;
    state.total = data.total;
    state.annotatedCount = data.annotated_count;
    state.currentIndex = 0;
    const typeLabel = data.source_type ? `[${data.source_type}]` : "";
    els.folderStatus.textContent = `已导入${typeLabel}: ${data.folder}（${data.total} 条）`;
    els.workspace.classList.remove("hidden");
    els.emptyState.classList.add("hidden");
    setNavEnabled(true);
    updateProgress();
    await loadItem(0);
    showToast("数据集导入成功");
  } catch (err) {
    showToast(err.message);
  }
}

function getSelectedLabels() {
  return [...els.labelsContainer.querySelectorAll("input[type=checkbox]:checked")]
    .map((input) => input.value);
}

async function saveAnnotation({ autoNext = false } = {}) {
  if (!state.currentItem) return;
  const payload = {
    id: state.currentItem.id,
    index: state.currentItem.index,
    labels: getSelectedLabels(),
    note: els.noteInput.value,
  };
  try {
    const data = await api("/api/annotate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    state.annotatedCount = data.annotated_count;
    updateProgress();
    showToast("保存成功");
    if (autoNext && state.currentIndex < state.total - 1) {
      await loadItem(state.currentIndex + 1);
    }
  } catch (err) {
    showToast(err.message);
  }
}

async function init() {
  try {
    const meta = await api("/api/meta");
    state.labels = meta.labels || [];
    renderLabels();
    if (meta.loaded) {
      state.loaded = true;
      state.total = meta.total;
      state.annotatedCount = meta.annotated_count;
      els.folderInput.value = meta.folder || "";
      const typeLabel = meta.source_type ? `[${meta.source_type}]` : "";
      els.folderStatus.textContent = `已导入${typeLabel}: ${meta.folder}（${meta.total} 条）`;
      els.workspace.classList.remove("hidden");
      els.emptyState.classList.add("hidden");
      setNavEnabled(true);
      updateProgress();
      await loadItem(0);
    }
  } catch (err) {
    showToast(err.message);
  }
}

els.btnOpen.addEventListener("click", openFolder);
els.btnBrowse.addEventListener("click", openBrowseModal);
els.btnBrowseClose.addEventListener("click", closeBrowseModal);
els.btnBrowseUp.addEventListener("click", () => {
  if (browseState.parent) loadBrowseDirectory(browseState.parent);
});
els.btnBrowseHome.addEventListener("click", () => {
  if (browseState.home) loadBrowseDirectory(browseState.home);
});
els.btnBrowseWorkspace.addEventListener("click", () => {
  if (browseState.workspace) loadBrowseDirectory(browseState.workspace);
});
els.btnBrowseSelect.addEventListener("click", () => selectBrowseFolder(false));
els.btnBrowseImport.addEventListener("click", () => selectBrowseFolder(true));
els.browseModal.addEventListener("click", (e) => {
  if (e.target === els.browseModal) closeBrowseModal();
});
els.btnPrev.addEventListener("click", () => {
  if (state.currentIndex > 0) loadItem(state.currentIndex - 1);
});
els.btnNext.addEventListener("click", () => {
  if (state.currentIndex < state.total - 1) loadItem(state.currentIndex + 1);
});
els.btnJump.addEventListener("click", () => {
  const idx = Number(els.jumpInput.value);
  if (Number.isInteger(idx) && idx >= 0 && idx < state.total) {
    loadItem(idx);
  } else {
    showToast("跳转 index 无效");
  }
});
els.btnRandom.addEventListener("click", jumpToRandom);
els.btnSave.addEventListener("click", () => saveAnnotation({ autoNext: true }));

els.lightbox.addEventListener("click", () => els.lightbox.classList.add("hidden"));
document.addEventListener("keydown", (e) => {
  if (!state.loaded) return;
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
    e.preventDefault();
    saveAnnotation({ autoNext: true });
    return;
  }
  const tag = e.target.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA") return;
  if (e.key === "r" || e.key === "R") {
    jumpToRandom();
    return;
  }
  if (e.key === "ArrowLeft" && state.currentIndex > 0) loadItem(state.currentIndex - 1);
  if (e.key === "ArrowRight" && state.currentIndex < state.total - 1) loadItem(state.currentIndex + 1);
});

init();
