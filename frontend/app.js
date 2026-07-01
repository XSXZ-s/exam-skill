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
const materialList = document.querySelector("#materialList");
const outputSelect = document.querySelector("#outputSelect");
const renderedPreview = document.querySelector("#renderedPreview");
const renderedContent = document.querySelector("#renderedContent");
const markdownPreview = document.querySelector("#markdownPreview");
const statusText = document.querySelector("#statusText");
const generationStatus = document.querySelector("#generationStatus");
const generationStatusText = document.querySelector("#generationStatusText");
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
const saveMarkdownBtn = document.querySelector("#saveMarkdownBtn");

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
saveMarkdownBtn.addEventListener("click", saveCurrentMarkdown);
renderTab.addEventListener("click", () => setPreviewMode("render"));
sourceTab.addEventListener("click", () => setPreviewMode("source"));
markdownPreview.addEventListener("input", () => {
  renderedContent.innerHTML = renderMarkdown(markdownPreview.value);
});
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
    hideGenerationStatus();
    setMarkdown("");
    setCurrentOutput("");
    return;
  }
  const subject = subjectSelect.value;
  const data = await requestJson(
    `/subjects/${encodeURIComponent(subject)}/outputs/${encodeURIComponent(filename)}`,
  );
  hideGenerationStatus();
  setMarkdown(data.markdown || "");
  setCurrentOutput(data.filename || filename);
}

async function analyze() {
  const subject = subjectSelect.value;
  const selectedFiles = selectedFilesForAnalysis();

  if (!selectedFiles.length) {
    showStatusError(new Error("请至少选择一个资料文件。"));
    return;
  }
  const score = Number(targetScore.value);
  if (!Number.isInteger(score) || score < 0 || score > 100) {
    showStatusError(new Error("目标分数需要是 0 到 100 之间的整数。"));
    return;
  }

  setBusy(true, "正在识别资料范围和类型...");
  showGenerationStatus("正在识别所选资料，请保持服务运行。");
  setMarkdown("");

  let payload;
  try {
    const materialPlan = await analyzeMaterials(subject, selectedFiles);
    payload = payloadFromMaterialPlan(materialPlan, score);
    if (!payload.knowledge_files.length || !payload.exam_files.length) {
      hideGenerationStatus();
      await handleMaterialClassificationMissing(materialPlan);
      return;
    }
    showGenerationStatus(`${materialPlan.summary} 正在生成复习方案...`);
    const result = await postAnalyze(subject, payload);
    hideGenerationStatus();
    setMarkdown(result.markdown || "");
    const outputFile = result.output_file || "";
    await loadOutputs(subject);
    if (outputFile) {
      outputSelect.value = outputFile;
      await readOutput(outputFile);
    }
    setBusy(false, `分析完成：${result.output_file || result.output_path}`);
  } catch (error) {
    if (error.status === 409 && error.detail && Array.isArray(error.detail.files)) {
      hideGenerationStatus();
      await handleLowQualityFiles(error.detail);
      return;
    }
    hideGenerationStatus();
    showStatusError(error);
  }
}

async function handleMaterialClassificationMissing(plan) {
  const summary = formatMaterialPlanSummary(plan);
  showManualTextConversionPrompt([
    "系统没有同时识别出“课件/知识资料”和“习题/出题参考资料”。",
    "",
    summary,
    "",
    "如果你选择的是图片、截图或扫描件，当前版本建议先手动转为文本类资料后再生成。",
    "也请确认本次同时选择了对应的课件和习题资料；如果文件名不清晰，可以标注“第x章课件 / 第x章习题”。",
  ]);
}

async function handleLowQualityFiles(detail) {
  const summary = detail.files
    .map((file) => `${file.path}：提取到 ${file.extracted_chars} 个字符，${file.chunk_count} 个片段`)
    .join("\n");
  showManualTextConversionPrompt([
    "检测到部分资料可提取文字较少，可能是扫描 PDF、图片型课件、截图题目，或文件解析失败。",
    "",
    summary,
    "",
    "当前版本暂不在前端提供 OCR 安装入口。为保证方案完整性，请先手动将这类资料转为 Markdown、TXT、Word 或可搜索 PDF 后再生成。",
  ]);
}

function showManualTextConversionPrompt(lines) {
  window.alert(
    [
      ...lines,
      "",
      "推荐格式：Markdown、TXT、Word 或可搜索 PDF。",
      "图片、截图和扫描件请先使用系统/WPS/微信等工具转文字后再放入 resources。当前生成已停止。",
    ].join("\n"),
  );
  setBusy(false, "请先将图片/扫描件手动转为文本类资料后再生成。");
}

async function postAnalyze(subject, payload) {
  return requestJson(`/subjects/${encodeURIComponent(subject)}/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
  });
}

async function analyzeMaterials(subject, files) {
  return requestJson(`/subjects/${encodeURIComponent(subject)}/materials/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ files }),
  });
}

function payloadFromMaterialPlan(plan, score) {
  const knowledge = new Set();
  const exam = new Set();
  const instruction = new Set();
  (plan.groups || []).forEach((group) => {
    (group.knowledge_files || []).forEach((file) => knowledge.add(file));
    (group.exam_files || []).forEach((file) => exam.add(file));
    (group.instruction_files || []).forEach((file) => instruction.add(file));
  });
  return {
    knowledge_files: Array.from(knowledge),
    exam_files: Array.from(exam),
    instruction_files: Array.from(instruction),
    material_groups: plan.groups || [],
    target_score: score,
  };
}

function formatMaterialPlanSummary(plan) {
  const groups = plan.groups || [];
  if (!groups.length) return "未识别到可用资料分组。";
  return groups
    .map((group) => {
      const parts = [];
      if ((group.knowledge_files || []).length) parts.push(`课件/知识：${group.knowledge_files.join("，")}`);
      if ((group.exam_files || []).length) parts.push(`习题/试卷：${group.exam_files.join("，")}`);
      if ((group.instruction_files || []).length) parts.push(`需求说明：${group.instruction_files.join("，")}`);
      if ((group.other_files || []).length) parts.push(`未分类：${group.other_files.join("，")}`);
      return `${group.chapter || group.group_id || "未识别分组"}：${parts.join("；") || "无可用文件"}`;
    })
    .join("\n");
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
    const materialPlan = await analyzeMaterials(subject, selectedMaterials());
    const materialPayload = payloadFromMaterialPlan(materialPlan, Number(targetScore.value));
    const response = await requestJson(`/subjects/${encodeURIComponent(subject)}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...materialPayload,
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

function selectedFilesForAnalysis() {
  return selectedMaterials();
}

function renderLists() {
  renderList(materialList, state.files, "material");
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
  materialList.innerHTML = `<div class="empty">${escapeHtml(message)}</div>`;
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

function selectedMaterials() {
  return selected("material");
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
  renderedContent.innerHTML = renderMarkdown(markdown);
}

function showGenerationStatus(message) {
  setPreviewMode("render");
  generationStatusText.textContent = message;
  generationStatus.hidden = false;
}

function hideGenerationStatus() {
  generationStatus.hidden = true;
}

function setPreviewMode(mode) {
  state.previewMode = mode;
  const isRender = mode === "render";
  renderedPreview.hidden = !isRender;
  markdownPreview.hidden = isRender;
  renderTab.classList.toggle("active", isRender);
  sourceTab.classList.toggle("active", !isRender);
}

async function saveCurrentMarkdown() {
  const subject = subjectSelect.value;
  const outputFile = state.currentOutput || outputSelect.value;
  if (!outputFile) {
    showStatusError(new Error("请先选择或生成一个输出文件。"));
    return;
  }
  const confirmed = window.confirm("保存会覆盖当前 output 中的 Markdown 文件，是否继续？");
  if (!confirmed) return;

  saveMarkdownBtn.disabled = true;
  try {
    const result = await requestJson(
      `/subjects/${encodeURIComponent(subject)}/outputs/${encodeURIComponent(outputFile)}`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ markdown: markdownPreview.value }),
      },
    );
    setMarkdown(result.markdown || "");
    setCurrentOutput(result.filename || outputFile);
    setBusy(false, `已保存：${result.filename || outputFile}`);
  } catch (error) {
    showStatusError(error);
  } finally {
    saveMarkdownBtn.disabled = false;
  }
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
  let displayMath = [];
  let inCode = false;
  let inDisplayMath = false;
  let displayMathEnd = "$$";

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
  const flushDisplayMath = () => {
    if (!displayMath.length) return;
    html.push(renderDisplayMath(displayMath.join("\n")));
    displayMath = [];
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

    const trimmedLine = line.trim();
    if (trimmedLine === "$$" || trimmedLine === "\\[") {
      if (inDisplayMath) {
        flushDisplayMath();
        inDisplayMath = false;
      } else {
        flushBlocks();
        inDisplayMath = true;
        displayMathEnd = trimmedLine === "\\[" ? "\\]" : "$$";
      }
      return;
    }

    if (inDisplayMath && trimmedLine === displayMathEnd) {
      flushDisplayMath();
      inDisplayMath = false;
      displayMathEnd = "$$";
      return;
    }

    if (inDisplayMath) {
      displayMath.push(line);
      return;
    }

    const singleLineMath = trimmedLine.match(/^\$\$(.+)\$\$$/);
    if (singleLineMath) {
      flushBlocks();
      html.push(renderDisplayMath(singleLineMath[1].trim()));
      return;
    }
    const singleLineBracketMath = trimmedLine.match(/^\\\[(.+)\\\]$/);
    if (singleLineBracketMath) {
      flushBlocks();
      html.push(renderDisplayMath(singleLineBracketMath[1].trim()));
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
  flushDisplayMath();
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
  const math = [];
  const stashMath = (expression) => {
    const token = `@@MATH_${math.length}@@`;
    math.push(renderInlineMath(expression.trim()));
    return token;
  };
  const textWithMathTokens = text
    .replace(/\\\((.+?)\\\)/g, (match, expression) => stashMath(expression))
    .replace(/(^|[^\\])\$([^$\n]+?)\$/g, (match, prefix, expression) => `${prefix}${stashMath(expression)}`);

  let html = escapeHtml(textWithMathTokens)
    .replace(/\\([*_`])/g, "$1")
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>')
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code>$1</code>");

  math.forEach((rendered, index) => {
    html = html.replace(`@@MATH_${index}@@`, rendered);
  });
  return html;
}

function renderDisplayMath(expression) {
  return `<div class="math-block">${renderMathExpression(expression)}</div>`;
}

function renderInlineMath(expression) {
  return `<span class="math-inline">${renderMathExpression(expression)}</span>`;
}

function renderMathExpression(expression) {
  let rendered = escapeHtml(expression.trim());
  rendered = renderLatexFractions(rendered);
  rendered = rendered
    .replace(/\\text\{([^{}]+)\}/g, '<span class="math-text">$1</span>')
    .replace(/\\mathrm\{([^{}]+)\}/g, '<span class="math-text">$1</span>')
    .replace(/\\times/g, "×")
    .replace(/\\cdot/g, "·")
    .replace(/(\S)\s*\*\s*(?=\S)/g, "$1×")
    .replace(/\\div/g, "÷")
    .replace(/\\sum/g, "∑")
    .replace(/\\Delta/g, "Δ")
    .replace(/\\mu/g, "μ")
    .replace(/\\alpha/g, "α")
    .replace(/\\beta/g, "β")
    .replace(/\\gamma/g, "γ")
    .replace(/\\rightarrow|\\to/g, "→")
    .replace(/\\leftrightarrow/g, "↔")
    .replace(/\\leq/g, "≤")
    .replace(/\\geq/g, "≥")
    .replace(/\\neq/g, "≠")
    .replace(/\\approx/g, "≈")
    .replace(/\\%/g, "%")
    .replace(/\\_/g, "_")
    .replace(/\^\{([^{}]+)\}/g, "<sup>$1</sup>")
    .replace(/_\{([^{}]+)\}/g, "<sub>$1</sub>")
    .replace(/\^([A-Za-z0-9+\-=]+)/g, "<sup>$1</sup>")
    .replace(/_([A-Za-z0-9+\-=]+)/g, "<sub>$1</sub>")
    .replace(/\\([A-Za-z]+)/g, "$1");
  return rendered;
}

function renderLatexFractions(expression) {
  let rendered = "";
  let index = 0;

  while (index < expression.length) {
    const fractionIndex = expression.indexOf("\\frac", index);
    if (fractionIndex === -1) {
      rendered += expression.slice(index);
      break;
    }

    rendered += expression.slice(index, fractionIndex);
    const numerator = readLatexGroup(expression, fractionIndex + "\\frac".length);
    if (!numerator) {
      rendered += "\\frac";
      index = fractionIndex + "\\frac".length;
      continue;
    }
    const denominator = readLatexGroup(expression, numerator.nextIndex);
    if (!denominator) {
      rendered += expression.slice(fractionIndex, numerator.nextIndex);
      index = numerator.nextIndex;
      continue;
    }

    rendered += `<span class="math-frac"><span class="math-num">${renderLatexFractions(numerator.value)}</span><span class="math-den">${renderLatexFractions(denominator.value)}</span></span>`;
    index = denominator.nextIndex;
  }

  return rendered;
}

function readLatexGroup(text, startIndex) {
  let index = startIndex;
  while (text[index] === " ") index += 1;
  if (text[index] !== "{") return null;

  let depth = 0;
  let value = "";
  for (; index < text.length; index += 1) {
    const char = text[index];
    if (char === "{") {
      if (depth > 0) value += char;
      depth += 1;
      continue;
    }
    if (char === "}") {
      depth -= 1;
      if (depth === 0) {
        return { value, nextIndex: index + 1 };
      }
      value += char;
      continue;
    }
    value += char;
  }

  return null;
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
    const message =
      typeof data.detail === "string"
        ? data.detail
        : data.detail && data.detail.message
          ? data.detail.message
          : `请求失败：${response.status}`;
    const error = new Error(message);
    error.status = response.status;
    error.detail = data.detail;
    throw error;
  }
  return data;
}

function setBusy(isBusy, message) {
  analyzeBtn.disabled = isBusy;
  refreshBtn.disabled = isBusy;
  saveMarkdownBtn.disabled = isBusy;
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

function delay(ms) {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}
