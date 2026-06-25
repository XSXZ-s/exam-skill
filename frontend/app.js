const state = {
  subjects: [],
  files: [],
  outputs: [],
  currentOutput: "",
  previewMode: "render",
};

const subjectSelect = document.querySelector("#subjectSelect");
const targetScore = document.querySelector("#targetScore");
const knowledgeList = document.querySelector("#knowledgeList");
const examList = document.querySelector("#examList");
const instructionList = document.querySelector("#instructionList");
const outputSelect = document.querySelector("#outputSelect");
const renderedPreview = document.querySelector("#renderedPreview");
const markdownPreview = document.querySelector("#markdownPreview");
const statusText = document.querySelector("#statusText");
const chatLog = document.querySelector("#chatLog");
const questionInput = document.querySelector("#questionInput");
const analyzeBtn = document.querySelector("#analyzeBtn");
const askBtn = document.querySelector("#askBtn");
const refreshBtn = document.querySelector("#refreshBtn");
const renderTab = document.querySelector("#renderTab");
const sourceTab = document.querySelector("#sourceTab");

refreshBtn.addEventListener("click", loadSubjects);
subjectSelect.addEventListener("change", async () => {
  await loadFiles(subjectSelect.value);
  await loadOutputs(subjectSelect.value);
});
outputSelect.addEventListener("change", () => readOutput(outputSelect.value));
analyzeBtn.addEventListener("click", analyze);
askBtn.addEventListener("click", askQuestion);
renderTab.addEventListener("click", () => setPreviewMode("render"));
sourceTab.addEventListener("click", () => setPreviewMode("source"));

document.querySelectorAll("[data-toggle]").forEach((button) => {
  button.addEventListener("click", () => toggleGroup(button.dataset.toggle));
});

loadSubjects();
setPreviewMode("render");

async function loadSubjects() {
  setBusy(true, "正在读取学科...");
  try {
    const data = await requestJson("/subjects");
    state.subjects = data.subjects || [];
    subjectSelect.innerHTML = state.subjects
      .map((subject) => `<option value="${escapeHtml(subject)}">${escapeHtml(subject)}</option>`)
      .join("");

    if (!state.subjects.length) {
      renderEmpty("resources 下还没有学科目录。");
      setBusy(false, "未发现学科。");
      return;
    }

    await loadFiles(state.subjects[0]);
    await loadOutputs(state.subjects[0]);
  } catch (error) {
    showStatusError(error);
  }
}

async function loadFiles(subject) {
  setBusy(true, "正在读取资料...");
  const data = await requestJson(`/subjects/${encodeURIComponent(subject)}/files`);
  state.files = data.files || [];
  renderLists();
  setBusy(false, `已读取 ${state.files.length} 个文件。`);
}

async function loadOutputs(subject) {
  const data = await requestJson(`/subjects/${encodeURIComponent(subject)}/outputs`);
  state.outputs = data.files || [];
  outputSelect.innerHTML = [
    '<option value="">选择历史输出</option>',
    ...state.outputs.map((file) => `<option value="${escapeHtml(file)}">${escapeHtml(file)}</option>`),
  ].join("");
  setMarkdown("");
  state.currentOutput = "";
}

async function readOutput(filename) {
  if (!filename) {
    setMarkdown("");
    state.currentOutput = "";
    return;
  }
  const subject = subjectSelect.value;
  const data = await requestJson(
    `/subjects/${encodeURIComponent(subject)}/outputs/${encodeURIComponent(filename)}`,
  );
  setMarkdown(data.markdown || "");
  state.currentOutput = data.filename || filename;
}

async function analyze() {
  const subject = subjectSelect.value;
  const payload = currentPayload();

  if (!payload.knowledge_files.length || !payload.exam_files.length) {
    showStatusError(new Error("知识库资料和出题参考资料都至少需要选择一个文件。"));
    return;
  }
  if (!Number.isInteger(payload.target_score) || payload.target_score < 0 || payload.target_score > 100) {
    showStatusError(new Error("目标分数需要是 0 到 100 之间的整数。"));
    return;
  }

  setBusy(true, "正在分析，首次运行可能需要较长时间...");
  setMarkdown("正在生成复习方案，请保持服务运行。");

  try {
    const result = await requestJson(`/subjects/${encodeURIComponent(subject)}/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    setMarkdown(result.markdown || "");
    state.currentOutput = result.output_file || "";
    await loadOutputs(subject);
    if (state.currentOutput) {
      outputSelect.value = state.currentOutput;
      await readOutput(state.currentOutput);
    }
    setBusy(false, `分析完成：${result.output_file || result.output_path}`);
  } catch (error) {
    showStatusError(error);
  }
}

async function askQuestion() {
  const question = questionInput.value.trim();
  const subject = subjectSelect.value;
  if (!question) {
    showStatusError(new Error("请输入追问内容。"));
    return;
  }
  if (!state.currentOutput && !outputSelect.value) {
    showStatusError(new Error("请先选择或生成一个输出文件。"));
    return;
  }

  appendChat("user", question);
  questionInput.value = "";
  askBtn.disabled = true;

  try {
    const response = await requestJson(`/subjects/${encodeURIComponent(subject)}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...currentPayload(),
        question,
        output_file: state.currentOutput || outputSelect.value,
      }),
    });
    appendChat("assistant", response.answer || "");
  } catch (error) {
    appendChat("assistant error", error.message);
  } finally {
    askBtn.disabled = false;
  }
}

function currentPayload() {
  return {
    knowledge_files: selected("knowledge"),
    exam_files: selected("exam"),
    instruction_files: selected("instruction"),
    target_score: Number(targetScore.value),
  };
}

function renderLists() {
  renderList(knowledgeList, state.files, "knowledge");
  renderList(examList, state.files, "exam");
  renderList(
    instructionList,
    state.files.filter((file) => /\.(txt|md)$/i.test(file)),
    "instruction",
  );
}

function renderList(container, files, group) {
  if (!files.length) {
    container.innerHTML = '<div class="empty">没有可选文件。</div>';
    return;
  }
  container.innerHTML = files
    .map((file) => {
      const id = `${group}-${hashCode(file)}`;
      return `
        <label class="file-item" for="${id}">
          <input id="${id}" type="checkbox" data-group="${group}" value="${escapeHtml(file)}" />
          <span class="file-name">${escapeHtml(file)}</span>
        </label>
      `;
    })
    .join("");
}

function renderEmpty(message) {
  [knowledgeList, examList, instructionList].forEach((container) => {
    container.innerHTML = `<div class="empty">${escapeHtml(message)}</div>`;
  });
}

function toggleGroup(group) {
  const boxes = Array.from(document.querySelectorAll(`input[data-group="${group}"]`));
  const shouldCheck = boxes.some((box) => !box.checked);
  boxes.forEach((box) => {
    box.checked = shouldCheck;
  });
}

function selected(group) {
  return Array.from(document.querySelectorAll(`input[data-group="${group}"]:checked`)).map(
    (input) => input.value,
  );
}

function appendChat(role, text) {
  const item = document.createElement("div");
  item.className = `chat-item ${role}`;
  if (role === "assistant") {
    item.innerHTML = marked.parse(text);
  } else {
    item.textContent = text;
  }
  chatLog.appendChild(item);
  chatLog.scrollTop = chatLog.scrollHeight;
}

function setMarkdown(markdown) {
  markdownPreview.value = markdown;
  renderedPreview.innerHTML = renderMarkdown(markdown);
}

function setPreviewMode(mode) {
  state.previewMode = mode;
  const isRender = mode === "render";
  renderedPreview.hidden = !isRender;
  markdownPreview.hidden = isRender;
  renderTab.classList.toggle("active", isRender);
  sourceTab.classList.toggle("active", !isRender);
}

function renderMarkdown(markdown) {
  if (!markdown.trim()) {
    return '<p class="empty">选择历史输出或生成新方案后，会在这里显示 Markdown 预览。</p>';
  }
  return marked.parse(markdown);
}

function renderTable(lines) {
  const rows = lines
    .filter((line) => !/^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line))
    .map((line) => line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((cell) => cell.trim()));
  if (!rows.length) return "";
  const [head, ...body] = rows;
  return `
    <table>
      <thead><tr>${head.map((cell) => `<th>${inlineMarkdown(cell)}</th>`).join("")}</tr></thead>
      <tbody>${body
        .map((row) => `<tr>${row.map((cell) => `<td>${inlineMarkdown(cell)}</td>`).join("")}</tr>`)
        .join("")}</tbody>
    </table>
  `;
}

function inlineMarkdown(text) {
  return escapeHtml(text)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code>$1</code>");
}

async function requestJson(url, options) {
  const response = await fetch(url, options);
  const text = await response.text();
  const data = text ? JSON.parse(text) : {};
  if (!response.ok) {
    throw new Error(data.detail || `请求失败：${response.status}`);
  }
  return data;
}

function setBusy(isBusy, message) {
  analyzeBtn.disabled = isBusy;
  refreshBtn.disabled = isBusy;
  statusText.textContent = message;
}

function showStatusError(error) {
  setBusy(false, `错误：${error.message}`);
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => {
    const entities = {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    };
    return entities[char];
  });
}

function hashCode(value) {
  let hash = 0;
  for (let i = 0; i < value.length; i += 1) {
    hash = (hash << 5) - hash + value.charCodeAt(i);
    hash |= 0;
  }
  return Math.abs(hash);
}
