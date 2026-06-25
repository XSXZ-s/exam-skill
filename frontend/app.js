const MAX_CHAT_MESSAGES = 30;

const state = {
  subjects: [],
  files: [],
  outputs: [],
  currentOutput: "",
  previewMode: "render",
  isAsking: false,
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
const chatStatus = document.querySelector("#chatStatus");
const questionInput = document.querySelector("#questionInput");
const analyzeBtn = document.querySelector("#analyzeBtn");
const askBtn = document.querySelector("#askBtn");
const refreshBtn = document.querySelector("#refreshBtn");
const renderTab = document.querySelector("#renderTab");
const sourceTab = document.querySelector("#sourceTab");
const clearChatBtn = document.querySelector("#clearChatBtn");
const printBtn = document.querySelector("#printBtn");

refreshBtn.addEventListener("click", loadSubjects);
subjectSelect.addEventListener("change", async () => {
  await loadFiles(subjectSelect.value);
  await loadOutputs(subjectSelect.value);
});
outputSelect.addEventListener("change", () => readOutput(outputSelect.value));
analyzeBtn.addEventListener("click", analyze);
askBtn.addEventListener("click", askQuestion);
clearChatBtn.addEventListener("click", clearCurrentChat);
printBtn.addEventListener("click", printCurrentPreview);
renderTab.addEventListener("click", () => setPreviewMode("render"));
sourceTab.addEventListener("click", () => setPreviewMode("source"));
questionInput.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
    askQuestion();
  }
});

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
      setMarkdown("");
      loadChatHistory();
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
  setCurrentOutput("");
}

async function readOutput(filename) {
  if (!filename) {
    setMarkdown("");
    setCurrentOutput("");
    return;
  }
  const subject = subjectSelect.value;
  const data = await requestJson(
    `/subjects/${encodeURIComponent(subject)}/outputs/${encodeURIComponent(filename)}`,
  );
  setMarkdown(data.markdown || "");
  setCurrentOutput(data.filename || filename);
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
    const outputFile = result.output_file || "";
    await loadOutputs(subject);
    if (outputFile) {
      outputSelect.value = outputFile;
      await readOutput(outputFile);
    }
    setBusy(false, `分析完成：${result.output_file || result.output_path}`);
  } catch (error) {
    showStatusError(error);
  }
}

async function askQuestion() {
  const question = questionInput.value.trim();
  const subject = subjectSelect.value;
  const outputFile = state.currentOutput || outputSelect.value;

  if (state.isAsking) return;
  if (!question) {
    showChatStatus("请输入追问内容。", true);
    return;
  }
  if (!outputFile) {
    showChatStatus("请先选择或生成一个输出文件。", true);
    return;
  }

  appendChat("user", question);
  questionInput.value = "";
  const pendingItem = appendChat("assistant", "AI 正在思考...", { pending: true, persist: false });
  setAsking(true);

  try {
    const response = await requestJson(`/subjects/${encodeURIComponent(subject)}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...currentPayload(),
        question,
        output_file: outputFile,
      }),
    });
    updateChatItem(pendingItem, "assistant", response.answer || "模型没有返回内容。");
    saveCurrentChat();
    showChatStatus("追问完成。");
  } catch (error) {
    updateChatItem(pendingItem, "assistant error", `请求失败：${error.message}`);
    saveCurrentChat();
    showChatStatus(`请求失败：${error.message}`, true);
  } finally {
    setAsking(false);
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

function setCurrentOutput(filename) {
  state.currentOutput = filename;
  loadChatHistory();
}

function chatStorageKey() {
  const subject = subjectSelect.value || "未选择学科";
  const outputFile = state.currentOutput || outputSelect.value || "未选择输出";
  return `exam-skill:chat:${subject}:${outputFile}`;
}

function loadChatHistory() {
  chatLog.innerHTML = "";
  const raw = localStorage.getItem(chatStorageKey());
  if (!raw) return;

  try {
    const messages = JSON.parse(raw);
    if (!Array.isArray(messages)) return;
    const recentMessages = messages.slice(-MAX_CHAT_MESSAGES);
    if (recentMessages.length !== messages.length) {
      localStorage.setItem(chatStorageKey(), JSON.stringify(recentMessages));
    }
    recentMessages.forEach((message) => {
      if (message && typeof message.role === "string" && typeof message.text === "string") {
        appendChat(message.role, message.text, { persist: false });
      }
    });
  } catch {
    localStorage.removeItem(chatStorageKey());
  }
}

function saveCurrentChat() {
  const messages = Array.from(chatLog.querySelectorAll(".chat-item"))
    .filter((item) => !item.dataset.pending)
    .map((item) => ({
      role: item.dataset.role || "assistant",
      text: item.dataset.text || item.textContent,
    }))
    .slice(-MAX_CHAT_MESSAGES);
  localStorage.setItem(chatStorageKey(), JSON.stringify(messages));
}

function clearCurrentChat() {
  localStorage.removeItem(chatStorageKey());
  chatLog.innerHTML = "";
  showChatStatus("当前对话已清空。");
}

function appendChat(role, text, options = {}) {
  const item = document.createElement("div");
  item.className = `chat-item ${role}${options.pending ? " pending" : ""}`;
  item.dataset.role = role;
  item.dataset.text = text;
  if (options.pending) item.dataset.pending = "true";
  renderChatItem(item, role, text);
  chatLog.appendChild(item);
  chatLog.scrollTop = chatLog.scrollHeight;
  if (options.persist !== false) saveCurrentChat();
  return item;
}

function updateChatItem(item, role, text) {
  item.className = `chat-item ${role}`;
  item.dataset.role = role;
  item.dataset.text = text;
  delete item.dataset.pending;
  renderChatItem(item, role, text);
  chatLog.scrollTop = chatLog.scrollHeight;
}

function renderChatItem(item, role, text) {
  if (role === "assistant") {
    item.innerHTML = renderMarkdown(text);
  } else {
    item.textContent = text;
  }
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

function printCurrentPreview() {
  if (!markdownPreview.value.trim()) {
    showStatusError(new Error("请先选择或生成一个输出文件。"));
    return;
  }
  setPreviewMode("render");
  document.title = state.currentOutput || outputSelect.value || "复习方案";
  window.print();
}

function renderMarkdown(markdown) {
  if (!markdown.trim()) {
    return '<p class="empty">选择历史输出或生成新方案后，会在这里显示 Markdown 预览。</p>';
  }

  const lines = markdown.replace(/\r\n/g, "\n").split("\n");
  const html = [];
  let paragraph = [];
  let list = [];
  let listTag = "ul";
  let table = [];
  let code = [];
  let quote = [];
  let inCode = false;

  const flushParagraph = () => {
    if (!paragraph.length) return;
    html.push(`<p>${inlineMarkdown(paragraph.join(" "))}</p>`);
    paragraph = [];
  };
  const flushList = () => {
    if (!list.length) return;
    html.push(`<${listTag}>${list.map((item) => `<li>${inlineMarkdown(item)}</li>`).join("")}</${listTag}>`);
    list = [];
    listTag = "ul";
  };
  const flushTable = () => {
    if (!table.length) return;
    html.push(renderTable(table));
    table = [];
  };
  const flushQuote = () => {
    if (!quote.length) return;
    html.push(`<blockquote>${quote.map((item) => `<p>${inlineMarkdown(item)}</p>`).join("")}</blockquote>`);
    quote = [];
  };
  const flushCode = () => {
    if (!code.length) return;
    html.push(`<pre><code>${escapeHtml(code.join("\n"))}</code></pre>`);
    code = [];
  };
  const flushBlocks = () => {
    flushParagraph();
    flushList();
    flushTable();
    flushQuote();
  };

  lines.forEach((line, index) => {
    if (/^```/.test(line.trim())) {
      if (inCode) {
        flushCode();
        inCode = false;
      } else {
        flushBlocks();
        inCode = true;
      }
      return;
    }

    if (inCode) {
      code.push(line);
      return;
    }

    if (isTableRow(line) && (table.length || isTableSeparator(lines[index + 1] || ""))) {
      flushParagraph();
      flushList();
      flushQuote();
      table.push(line);
      return;
    }

    flushTable();
    const heading = line.match(/^(#{1,6})\s+(.+)$/);
    const bullet = line.match(/^\s*[-*+]\s+(.+)$/);
    const numbered = line.match(/^\s*\d+\.\s+(.+)$/);
    const quoteLine = line.match(/^\s*>\s?(.+)$/);

    if (heading) {
      flushParagraph();
      flushList();
      flushQuote();
      const level = Math.min(heading[1].length, 6);
      html.push(`<h${level}>${inlineMarkdown(heading[2])}</h${level}>`);
    } else if (bullet) {
      flushParagraph();
      flushQuote();
      if (list.length && listTag !== "ul") flushList();
      listTag = "ul";
      list.push(bullet[1]);
    } else if (numbered) {
      flushParagraph();
      flushQuote();
      if (list.length && listTag !== "ol") flushList();
      listTag = "ol";
      list.push(numbered[1]);
    } else if (quoteLine) {
      flushParagraph();
      flushList();
      quote.push(quoteLine[1]);
    } else if (/^\s*(-{3,}|\*{3,}|_{3,})\s*$/.test(line)) {
      flushBlocks();
      html.push("<hr>");
    } else if (!line.trim()) {
      flushBlocks();
    } else {
      flushList();
      flushQuote();
      paragraph.push(line.trim());
    }
  });

  flushCode();
  flushBlocks();
  return html.join("");
}

function isTableRow(line) {
  return /^\s*\|.+\|\s*$/.test(line);
}

function isTableSeparator(line) {
  return /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line);
}

function renderTable(lines) {
  const rows = lines
    .filter((line) => !isTableSeparator(line))
    .map((line) =>
      line
        .trim()
        .replace(/^\|/, "")
        .replace(/\|$/, "")
        .split("|")
        .map((cell) => cell.trim()),
    );
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
    .replace(/\\([*_`])/g, "$1")
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>')
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code>$1</code>");
}

async function requestJson(url, options) {
  let response;
  try {
    response = await fetch(url, options);
  } catch {
    throw new Error("无法连接后端服务，请确认 run_api.bat 的终端还在运行。");
  }

  const text = await response.text();
  let data = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    throw new Error(text || `请求失败：${response.status}`);
  }

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

function setAsking(isAsking) {
  state.isAsking = isAsking;
  askBtn.disabled = isAsking;
  askBtn.textContent = isAsking ? "思考中..." : "发送追问";
  if (isAsking) {
    showChatStatus("正在等待模型回复...");
  }
}

function showStatusError(error) {
  setBusy(false, `错误：${error.message}`);
}

function showChatStatus(message, isError = false) {
  chatStatus.textContent = message;
  chatStatus.classList.toggle("error", isError);
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
