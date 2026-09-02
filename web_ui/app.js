/* ══════════════════════════════════════════════════════════════════════════
 * CoderAI Web Client - Modular Architecture
 * ══════════════════════════════════════════════════════════════════════════ */

/* ── 1. GLOBAL STATE & SELECTOR HELPERS ─────────────────────────── */
const state = {
  data: null,
  activeFile: null,
  fileContent: "",
  generatedInfo: "txt",
  editorDirty: false,
  contextUsage: {},
  workspaceLocked: false,
  pendingApprovalType: null,
  pendingPush: null,
  projectCards: [],
  projectArchive: null,
  initialProjectsShown: false,
  commandSelection: 0,
};

const $ = (id) => document.getElementById(id);

function installEditorMetricStyles() {
  if (document.getElementById("editorMetricStyles")) return;
  const style = document.createElement("style");
  style.id = "editorMetricStyles";
  style.textContent = `
    .code-highlight,
    .code-highlight code,
    .code-editor {
      font-family: Consolas, "SFMono-Regular", "Cascadia Mono", "IBM Plex Mono", ui-monospace, monospace !important;
      font-size: 13px !important;
      font-weight: 400 !important;
      line-height: 20px !important;
      letter-spacing: 0 !important;
      word-spacing: 0 !important;
      tab-size: 2 !important;
      font-variant-ligatures: none !important;
      font-kerning: none !important;
      white-space: pre !important;
      overflow-wrap: normal !important;
      word-break: normal !important;
    }
    .code-highlight,
    .code-editor {
      padding: 16px 16px 16px 62px !important;
      overflow: auto !important;
    }
    .code-highlight code {
      display: block !important;
      min-width: max-content !important;
    }
    .code-editor {
      -webkit-text-size-adjust: 100%;
      text-size-adjust: 100%;
    }
  `;
  document.head.appendChild(style);
}

function getActiveSessionId() {
  let sid = sessionStorage.getItem("coderai_session_id");
  if (!sid) {
    sid = "sess_" + Math.random().toString(36).slice(2, 10);
    sessionStorage.setItem("coderai_session_id", sid);
  }
  return sid;
}

async function api(path, options = {}) {
  const headers = {
    "Content-Type": "application/json",
    "X-Session-ID": getActiveSessionId(),
    ...(options.headers || {}),
  };
  const res = await fetch(path, {
    ...options,
    headers,
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || data.message || "Request failed");
  return data;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes}b`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)}KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)}MB`;
}

function formatTokens(value) {
  const num = Number(value || 0);
  if (num >= 1000000) return `${(num / 1000000).toFixed(num >= 10000000 ? 0 : 1)}M`;
  if (num >= 1000) return `${(num / 1000).toFixed(num >= 10000 ? 0 : 1)}K`;
  return String(Math.max(0, Math.round(num)));
}

function extensionForInfo(info) {
  const lang = String(info || "txt").trim().split(/\s+/)[0].toLowerCase();
  const map = {
    javascript: "js",
    js: "js",
    typescript: "ts",
    ts: "ts",
    tsx: "tsx",
    jsx: "jsx",
    python: "py",
    py: "py",
    html: "html",
    css: "css",
    json: "json",
    markdown: "md",
    md: "md",
    shell: "sh",
    bash: "sh",
    powershell: "ps1",
    ps1: "ps1",
    yaml: "yml",
    yml: "yml",
    sql: "sql",
  };
  return map[lang] || lang.replace(/[^a-z0-9]/g, "") || "txt";
}

function languageForInfo(info) {
  const lang = String(info || "text").trim().split(/\s+/)[0].toLowerCase();
  const map = {
    py: "python",
    python: "python",
    js: "javascript",
    javascript: "javascript",
    jsx: "javascript",
    ts: "typescript",
    tsx: "typescript",
    typescript: "typescript",
    java: "java",
    html: "html",
    htm: "html",
    css: "css",
    json: "json",
    md: "markdown",
    markdown: "markdown",
    sh: "shell",
    bash: "shell",
    shell: "shell",
    ps1: "powershell",
    powershell: "powershell",
    sql: "sql",
    yml: "yaml",
    yaml: "yaml",
  };
  return map[lang] || "text";
}

function tokenClass(token, language) {
  const keywordSets = {
    python: "and as assert async await break class continue def del elif else except False finally for from global if import in is lambda None nonlocal not or pass raise return True try while with yield self",
    javascript: "await async break case catch class const continue debugger default delete do else export extends false finally for from function if import in instanceof let new null return static super switch this throw true try typeof undefined var void while yield",
    typescript: "abstract any as async await boolean break case catch class const constructor continue declare default delete do else enum export extends false finally for from function if implements import in instanceof interface keyof let module namespace never new null number private protected public readonly return static string super switch this throw true try type typeof undefined unknown var void while yield",
    java: "abstract assert boolean break byte case catch char class const continue default do double else enum extends false final finally float for if implements import instanceof int interface long native new null package private protected public return short static strictfp super switch synchronized this throw throws transient true try void volatile while",
    css: "align-items animation background border bottom color content display flex font grid height justify-content left margin max-width min-height opacity overflow padding place-items position right text top transform transition width z-index",
    shell: "case do done elif else esac fi for function if in local return then while",
    powershell: "begin break catch class continue data do dynamicparam else elseif end exit filter finally for foreach from function if in param process return switch throw trap try until using var while",
    sql: "alter and as by case create delete desc distinct drop else end from group having in insert into is join left like limit not null on or order outer right select set table then update values when where",
  };
  const keywords = new Set((keywordSets[language] || "").split(/\s+/).filter(Boolean));
  if (/^\/\*[\s\S]*\*\/$/.test(token) || /^\/\/.*/.test(token) || /^#.*/.test(token) || /^<!--[\s\S]*-->$/.test(token)) return "tok-comment";
  if (/^["'`]/.test(token) || /^"""[\s\S]*"""$/.test(token) || /^'''[\s\S]*'''$/.test(token)) return "tok-string";
  if (/^\b\d/.test(token)) return "tok-number";
  if (language === "html" && /^<\/?[\w:-]+/.test(token)) return "tok-tag";
  if (language === "css" && /^[.#]?[-_a-zA-Z][-_a-zA-Z0-9]*(?=\s*:|\s*\{)/.test(token)) return "tok-selector";
  if (keywords.has(token)) return "tok-keyword";
  if (/^[A-Z][A-Za-z0-9_]*$/.test(token)) return "tok-type";
  return "";
}

function highlightCode(code, info = "text") {
  const language = languageForInfo(info);
  if (!code) return "";
  if (language === "json") {
    return escapeHtml(code).replace(
      /(&quot;(?:\\.|[^&])*?&quot;)(\s*:)?|\b(true|false|null)\b|-?\b\d+(?:\.\d+)?(?:e[+-]?\d+)?\b/gi,
      (match, stringToken, colon, boolToken) => {
        if (stringToken) return `<span class="${colon ? "tok-property" : "tok-string"}">${stringToken}</span>${colon || ""}`;
        if (boolToken) return `<span class="tok-keyword">${match}</span>`;
        return `<span class="tok-number">${match}</span>`;
      }
    );
  }

  const commentPrefix = ["python", "shell", "powershell", "yaml"].includes(language) ? "#.*" : "\\/\\/.*";
  const tokenPattern = new RegExp(
    "\\/\\*[\\s\\S]*?\\*\\/|<!--([\\s\\S]*?)-->|" +
      commentPrefix +
      "|\"\"\"[\\s\\S]*?\"\"\"|'''[\\s\\S]*?'''|\"(?:\\\\.|[^\"\\\\])*\"|'(?:\\\\.|[^'\\\\])*'|`(?:\\\\.|[^`\\\\])*`|<\\/?[\\w:-]+(?:\\s+[^<>]*)?>|\\b\\d+(?:\\.\\d+)?\\b|\\b[A-Za-z_$][\\w$]*\\b",
    "g"
  );
  let html = "";
  let last = 0;
  for (const match of code.matchAll(tokenPattern)) {
    const token = match[0];
    html += escapeHtml(code.slice(last, match.index));
    const cls = tokenClass(token, language);
    html += cls ? `<span class="${cls}">${escapeHtml(token)}</span>` : escapeHtml(token);
    last = match.index + token.length;
  }
  html += escapeHtml(code.slice(last));
  return html;
}

function setCodeEditorContent(title, meta, content, info = "txt") {
  state.activeFile = title;
  state.fileContent = content || "";
  state.generatedInfo = info || "txt";
  state.editorDirty = false;
  const language = languageForInfo(state.generatedInfo);
  $("activeFile").textContent = title;
  $("fileMeta").textContent = meta;
  $("editorLanguage").textContent = language;
  $("codeEditor").value = state.fileContent;
  $("codeEditor").disabled = false;
  $("codeEditorWrap").classList.toggle("empty", !state.fileContent);
  renderCodeHighlight();
  $("attachFile").disabled = !state.fileContent;
  $("downloadCode").disabled = !state.fileContent;
  updateTokenUsage();
}

function renderCodeHighlight() {
  const code = $("codeEditor").value;
  const visibleCode = code || "Select or generate code to edit it here.";
  const highlight = $("codeHighlight");
  if (highlight) {
    highlight.innerHTML = `<code>${highlightCode(visibleCode, state.generatedInfo)}</code>`;
  }
  syncEditorHighlightScroll();
}

function setCodePreview(title, meta, content, info = "txt") {
  setCodeEditorContent(title, meta, content, info);
}

function syncEditorHighlightScroll() {
  const highlight = $("codeHighlight");
  const editor = $("codeEditor");
  if (!highlight || !editor) return;
  highlight.scrollTop = editor.scrollTop;
  highlight.scrollLeft = editor.scrollLeft;
}

function activateTab(name) {
  document.body.classList.toggle("utility-mode", name !== "files");
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
  document.querySelectorAll(".tab-page").forEach((p) => p.classList.remove("active"));
  $(`${name}Tab`)?.classList.add("active");
}

function setActiveActivity(label) {
  document.querySelectorAll(".activity-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.getAttribute("aria-label") === label);
  });
}

function renderState(data) {
  state.data = data;
  const ws = data.workspace;
  $("workspacePath").textContent = ws.path;
  if ($("statusModel")) $("statusModel").textContent = data.settings.model || "Model ready";
  const gitBranch = data.git?.status?.branch || data.git?.branch || "not connected";
  $("statusBranch").textContent = `Git: ${gitBranch}`;
  const index = data.code_index || {};
  $("statusIndex").textContent = !index.files ? "Index: not built" : index.up_to_date === false ? "Index: changes detected" : `Index: ${index.files} files`;
  $("statusModel").textContent = `Model: ${data.settings.model || "not selected"}`;
  $("workspaceInput").value = ws.path;
  $("fileCount").textContent = ws.stats.files;
  $("totalKb").textContent = `${ws.stats.kb}KB`;
  $("typeCount").textContent = ws.stats.types;
  $("connMode").value = data.settings.conn_mode;
  renderModels(data.models || { models: [], error: null }, data.settings.model);
  $("temperature").value = data.settings.temperature;
  $("thinking").checked = !!data.settings.enable_thinking;
  $("autoContinue").checked = !!data.settings.auto_continue;
  $("memoryEnabled").checked = !!data.settings.memory_enabled;
  $("contextTokenBudget").value = data.settings.context_token_budget || 24000;
  $("responseTokenBudget").value = data.settings.response_token_budget || 8192;
  $("tavilyEnabled").checked = !!data.settings.tavily_enabled;
  $("gitApprovalMode").checked = data.settings.git_approval_mode !== false;
  $("smartSkillConfirmation").checked = !!data.settings.smart_skill_confirmation;
  $("tavilyApiKey").value = "";
  updateTavilyPanel(data.settings);
  const memory = data.memory || {};
  const persistentStats = memory.persistent?.stats || {};
  $("memoryStats").textContent = `Memory: ${persistentStats.turns || 0} turns · ${persistentStats.facts || 0} facts · ${persistentStats.preferences || 0} preferences`;
  $("memoryUsageIndicator").textContent = memory.persistent?.retrieval_count
    ? `${memory.persistent.retrieval_count} memory fact(s) used`
    : "";
  state.contextUsage = data.context_usage || {};
  $("statusContext").textContent = `Context: ${Number(state.contextUsage.percent || 0)}%`;
  updateTokenUsage();
  $("customApiUrl").value = data.settings.custom_api_url || "https://api.openai.com/v1";
  $("topCustomApiUrl").value = data.settings.custom_api_url || "https://api.openai.com/v1";
  $("customApiModel").value = data.settings.custom_api_model || "gpt-4o-mini";
  $("topCustomApiModel").value = data.settings.custom_api_model || "gpt-4o-mini";
  $("customApiKey").value = "";
  $("topCustomApiKey").value = "";
  if ($("sandboxMode")) $("sandboxMode").value = data.settings.sandbox_mode || "auto";
  if ($("sandboxDockerImage")) $("sandboxDockerImage").value = data.settings.sandbox_docker_image || "python:3.11-slim";
  updateCustomApiPanel();
  $("systemPromptEditor").value = data.settings.system_prompt || "";
  $("selectedPromptName").textContent = data.settings.selected_prompt || "Custom system prompt";
  renderFiles();
  renderCodeIndex(data.code_index || {});
  renderSkills();
  renderPrompts();
  renderMemory(data.memory?.persistent || {});
  renderGit(data.git || {});
  renderMessages();
  if (!renderGeneratedArtifactFromState()) {
    renderGeneratedCodeFromMessages();
  }
  if (state.workspaceLocked) setWorkspaceLocked(true);
}

function friendlyErrorMessage(message) {
  const text = String(message || "");
  const lower = text.toLowerCase();
  if (lower.includes("chromadb") || lower.includes("chroma")) {
    return "Advanced semantic memory is unavailable, so the app is using the local fallback search mode.";
  }
  if (lower.includes("sqlite") && lower.includes("fallback")) {
    return "Local fallback search is active. You can keep working normally; semantic search may be less precise.";
  }
  if (lower.includes("tavily")) {
    return "Web search is not ready. Enable it from Settings when you need web results.";
  }
  if (lower.includes("module not found") || lower.includes("modulenotfounderror")) {
    return "An optional advanced component is missing. The app switched to a simpler local mode.";
  }
  if (lower.includes("timed out") || lower.includes("timeout")) {
    return "The selected model took too long to respond. Check that it is running, then try again.";
  }
  if (lower.includes("connection refused") || lower.includes("failed to fetch") || lower.includes("not reachable")) {
    return "The selected model service is unavailable. Check the connection in Settings and try again.";
  }
  if (lower.includes("traceback") || lower.includes("error:") || lower.includes("exception")) {
    return "The operation could not be completed. Check Advanced Settings or the application logs for technical details.";
  }
  return text || "The operation could not be completed.";
}

const commandDefinitions = [
  { id: "projects", icon: "P", title: "Projects and sessions", detail: "Browse local workspaces and resume previous sessions", keywords: "/session archive history", shortcut: "" },
  { id: "files", icon: "F", title: "Project files", detail: "Open the workspace file browser", keywords: "/file source tree", shortcut: "" },
  { id: "index", icon: "I", title: "Codebase intelligence", detail: "View project overview, index status, and dependency graph", keywords: "/index rag graph architecture", shortcut: "" },
  { id: "agent", icon: "A", title: "Agent chat", detail: "Focus the request composer", keywords: "/agent chat prompt", shortcut: "" },
  { id: "skills", icon: "S", title: "Skills", detail: "Choose skills and inspect usage", keywords: "/skill capability", shortcut: "" },
  { id: "prompts", icon: ">_", title: "System prompts", detail: "Select or edit the active system prompt", keywords: "/prompt system instruction", shortcut: "" },
  { id: "memory", icon: "M", title: "Memory", detail: "Browse sessions, project facts, and preferences", keywords: "/memory fact preference", shortcut: "" },
  { id: "git", icon: "G", title: "Git history", detail: "Review repository status, commits, clone, and push", keywords: "/git diff commit history", shortcut: "" },
  { id: "settings", icon: "CFG", title: "Settings", detail: "Model, runtime, and web search controls", keywords: "/settings model tavily", shortcut: "" },
  { id: "advanced", icon: "...", title: "Advanced settings", detail: "Context, memory, Git review, skills, and Custom API", keywords: "/advanced context api embedding", shortcut: "" },
];

function filteredCommands() {
  const query = $("commandSearch").value.trim().toLowerCase();
  if (!query) return commandDefinitions;
  return commandDefinitions.filter((command) => `${command.title} ${command.detail} ${command.keywords}`.toLowerCase().includes(query));
}

function renderCommandPalette() {
  const commands = filteredCommands();
  state.commandSelection = Math.max(0, Math.min(state.commandSelection, commands.length - 1));
  $("commandList").innerHTML = commands.map((command, index) => `
    <button type="button" class="command-item ${index === state.commandSelection ? "selected" : ""}" data-command-id="${command.id}" role="option" aria-selected="${index === state.commandSelection}">
      <span class="command-item-icon">${escapeHtml(command.icon)}</span>
      <span><strong>${escapeHtml(command.title)}</strong><span>${escapeHtml(command.detail)}</span></span>
      ${command.shortcut ? `<kbd>${escapeHtml(command.shortcut)}</kbd>` : ""}
    </button>
  `).join("") || `<div class="command-empty">No matching commands</div>`;
  document.querySelectorAll(".command-item").forEach((button) => button.addEventListener("click", () => runCommand(button.dataset.commandId)));
}

function openCommandPalette() {
  $("commandPalette").hidden = false;
  $("commandSearch").value = "";
  state.commandSelection = 0;
  renderCommandPalette();
  $("commandSearch").focus();
}

function closeCommandPalette() {
  $("commandPalette").hidden = true;
}

async function runCommand(id) {
  closeCommandPalette();
  if (id === "projects") return showProjects();
  showWorkbench();
  if (id === "files") { setActiveActivity("Files"); activateTab("files"); return $("fileSearch").focus(); }
  if (id === "index") { setActiveActivity("Files"); activateTab("files"); return activateFileView("index"); }
  if (id === "agent") { activateTab("files"); setActiveActivity("Agent"); return $("promptInput").focus(); }
  if (id === "skills") return activateTab("skills");
  if (id === "prompts") return activateTab("prompts");
  if (id === "memory") return activateTab("memory");
  if (id === "git") { activateTab("files"); return showEditorView("git"); }
  if (id === "settings" || id === "advanced") {
    setActiveActivity("Settings");
    activateTab("settings");
    const advanced = document.querySelector(".advanced-settings");
    if (id === "advanced") advanced.open = true;
  }
}

function formatRelativeTime(timestamp) {
  if (!timestamp) return "No activity";
  const seconds = Math.max(0, Math.floor(Date.now() / 1000 - Number(timestamp)));
  if (seconds < 60) return "Just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  if (seconds < 604800) return `${Math.floor(seconds / 86400)}d ago`;
  return new Date(Number(timestamp) * 1000).toLocaleDateString();
}

function showWorkbench() {
  document.querySelector(".layout").classList.remove("hidden");
  $("projectsView").classList.remove("active");
}

async function showProjects() {
  document.querySelector(".layout").classList.add("hidden");
  $("projectsView").classList.add("active");
  $("projectsIndex").classList.remove("hidden");
  $("projectHome").classList.remove("active");
  const payload = await api("/api/projects");
  state.projectCards = payload.projects || [];
  renderProjectCards();
}

async function deleteProject(projectId, projectName) {
  const confirmed = confirm(`Are you sure you want to remove project "${projectName || 'this project'}" from the workspace list?`);
  if (!confirmed) return;
  try {
    const res = await api("/api/project/delete", {
      method: "POST",
      body: JSON.stringify({ project_id: projectId }),
    });
    state.projectCards = res.projects || [];
    renderProjectCards();
    if ($("projectHome").classList.contains("active")) {
      $("projectHome").classList.remove("active");
      $("projectsIndex").classList.remove("hidden");
    }
  } catch (err) {
    alert(`Failed to delete project: ${err.message}`);
  }
}

function renderProjectCards() {
  $("projectCards").innerHTML = state.projectCards.map((project) => {
    const dirty = Number(project.git?.files?.length || 0);
    const gitClass = dirty ? "git-dirty" : "git-clean";
    const gitText = project.git?.is_repo ? `${dirty ? `${dirty} changes` : "Git clean"} · ${project.git.commits || 0} commits` : "Git disabled";
    return `<div class="project-card" data-project-id="${Number(project.id)}" role="button" tabindex="0">
      <div class="project-card-actions">
        <button type="button" class="project-card-delete-btn" data-project-id="${Number(project.id)}" data-project-name="${escapeHtml(project.name)}" title="Remove project">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" style="width:14px;height:14px"><path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/></svg>
        </button>
      </div>
      <div class="project-card-head"><span class="project-card-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z"/></svg></span><span class="project-card-title"><strong>${escapeHtml(project.name)}</strong><code>${escapeHtml(project.workspace_path)}</code></span></div>
      <div class="project-card-badges"><span class="project-badge ${gitClass}">${escapeHtml(gitText)}</span><span class="project-badge ${project.agent_status === "running" ? "running" : ""}">${escapeHtml(project.agent_status)}</span></div>
      <div class="project-card-footer"><span>${project.sessions || 0} sessions · ${project.stats?.files || 0} files · ${formatSize(Number(project.stats?.kb || 0) * 1024)}</span><span>${formatRelativeTime(project.last_session_at || project.last_opened_at)}</span></div>
    </div>`;
  }).join("") || `<div class="memory-item-source">No projects yet. Use + New to add a workspace.</div>`;

  document.querySelectorAll(".project-card").forEach((card) => {
    card.addEventListener("click", (e) => {
      if (e.target.closest(".project-card-delete-btn")) return;
      openProjectHome(Number(card.dataset.projectId));
    });
  });

  document.querySelectorAll(".project-card-delete-btn").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      deleteProject(Number(btn.dataset.projectId), btn.dataset.projectName);
    });
  });
}

async function openProjectHome(projectId) {
  const archive = await api("/api/memory/archive", { method: "POST", body: JSON.stringify({ project_id: projectId }) });
  const card = state.projectCards.find((item) => Number(item.id) === projectId) || archive.project || {};
  state.projectArchive = { ...archive, card };
  $("projectsIndex").classList.add("hidden");
  $("projectHome").classList.add("active");
  $("projectHomeName").textContent = card.name || "Project";
  $("projectHomePath").textContent = card.workspace_path || "";
  $("projectSettingsPath").textContent = card.workspace_path || "";
  $("projectSettingsGit").textContent = card.git?.is_repo ? `${card.git.branch || "Git"} · ${card.git.files?.length || 0} changes` : "Disabled";
  if ($("deleteProjectBtn")) {
    $("deleteProjectBtn").onclick = () => deleteProject(projectId, card.name);
  }
  renderProjectHome();
  activateProjectTab("overview");
}

function renderProjectHome() {
  const { card, sessions = [], files = [], facts = [], preferences = {}, skill_usage = {} } = state.projectArchive || {};
  const dirty = Number(card?.git?.files?.length || 0);
  $("projectQuickStats").innerHTML = [
    [card?.stats?.files || 0, "Files"], [formatSize(Number(card?.stats?.kb || 0) * 1024), "Workspace size"],
    [sessions.length, "Sessions"], [facts.length, "Saved facts"],
  ].map(([value, label]) => `<div class="quick-stat"><strong>${escapeHtml(value)}</strong><span>${label}</span></div>`).join("");
  const recent = sessions.slice(0, 5).map((session) => `<div class="activity-row"><i class="activity-dot"></i><div><strong>${escapeHtml(session.title)}</strong><span>${session.turns} turns · session</span></div><span>${formatRelativeTime(session.updated_at)}</span></div>`);
  if (card?.git?.is_repo) recent.unshift(`<div class="activity-row"><i class="activity-dot"></i><div><strong>${dirty ? `${dirty} uncommitted changes` : "Working tree clean"}</strong><span>${escapeHtml(card.git.branch || "Git")}</span></div><span>${card.git.commits || 0} commits</span></div>`);
  $("projectRecentActivity").innerHTML = recent.join("") || `<div class="memory-item-source">No recent activity.</div>`;
  const pct = Number(state.contextUsage?.percent || 0);
  $("projectContextFill").style.width = `${Math.min(100, pct)}%`;
  $("projectContextText").textContent = `${pct}%`;
  $("projectSessionList").innerHTML = sessions.map((session) => `<button type="button" class="project-session-row" data-session-id="${escapeHtml(session.id)}"><i class="activity-dot"></i><div><strong>${escapeHtml(session.title)}</strong><span>${session.turns} turns · ${escapeHtml(state.data?.settings?.model || "model")}</span></div><span>${formatRelativeTime(session.updated_at)}</span></button>`).join("") || `<div class="memory-item-source">No sessions for this project.</div>`;
  $("projectFileGrid").innerHTML = files.map((file) => `<button type="button" class="project-file-row" data-path="${escapeHtml(file.path)}"><span>${escapeHtml(file.path)}</span><small>${formatSize(file.size)}</small></button>`).join("") || `<div class="memory-item-source">No files found.</div>`;
  $("projectMemoryContent").innerHTML = `<section class="project-memory-group"><h2>Semantic Facts</h2><ul>${facts.map((fact) => `<li>${escapeHtml(fact.fact)}</li>`).join("") || "<li>No saved facts</li>"}</ul></section><section class="project-memory-group"><h2>Preferences</h2><ul>${Object.entries(preferences).map(([key, value]) => `<li><strong>${escapeHtml(key)}</strong>: ${escapeHtml(value)}</li>`).join("") || "<li>No saved preferences</li>"}</ul></section>`;
  $("projectSkillsContent").innerHTML = (skill_usage.skills || []).map((skill) => `<button type="button" class="project-skill ${skill.disabled ? "disabled" : ""}" data-skill-name="${escapeHtml(skill.name)}"><strong>/${escapeHtml(skill.name)}</strong><span>${skill.project_uses} project uses · ${skill.global_uses} global · ${skill.success_rate == null ? "no outcomes" : `${skill.success_rate}% success`}</span><span>${skill.top_keywords?.length ? `Top triggers: ${skill.top_keywords.map(([word]) => escapeHtml(word)).join(", ")}` : "No trigger keywords yet"}</span></button>`).join("");
  renderRoutingNotice("projectSkillsRoutingNotice", skill_usage.routing || {});
  document.querySelectorAll(".project-session-row").forEach((button) => button.addEventListener("click", () => resumeProjectSession(button.dataset.sessionId)));
  document.querySelectorAll(".project-file-row").forEach((button) => button.addEventListener("click", async () => { await openProjectInEditor(false); await loadFile(button.dataset.path); }));
  document.querySelectorAll(".project-skill").forEach((button) => button.addEventListener("click", () => showProjectSkillDetail(button.dataset.skillName)));
}

async function showProjectSkillDetail(name) {
  const source = await api(`/api/skill/source?name=${encodeURIComponent(name)}`);
  const stats = (state.projectArchive?.skill_usage?.skills || []).find((skill) => skill.name === name) || {};
  $("projectSkillDetail").innerHTML = `<div class="project-skill-detail-head"><div><h2>/${escapeHtml(name)}</h2><span>${stats.project_uses || 0} project uses · ${stats.global_uses || 0} global · ${stats.success_rate == null ? "No success data" : `${stats.success_rate}% success`}</span></div><label>Mode <select id="projectSkillMode"><option value="auto">Auto</option><option value="pinned">Pinned</option><option value="off">Off</option></select></label></div><textarea id="projectSkillSource" spellcheck="false"></textarea><div class="project-skill-detail-actions"><code>${escapeHtml(source.path)}</code><button id="saveProjectSkill" type="button" class="primary">Save SKILL.md</button></div>`;
  $("projectSkillSource").value = source.content;
  $("projectSkillMode").value = stats.mode || "auto";
  $("projectSkillMode").addEventListener("change", async () => {
    const updated = await api("/api/skills/mode", { method: "POST", body: JSON.stringify({ skill_name: name, mode: $("projectSkillMode").value, workspace_path: state.projectArchive?.card?.workspace_path }) });
    state.projectArchive.skill_usage = updated.skill_usage;
    renderProjectHome(); showProjectSkillDetail(name);
  });
  $("saveProjectSkill").addEventListener("click", async () => {
    await api("/api/skill/source", { method: "POST", body: JSON.stringify({ name, content: $("projectSkillSource").value }) });
    $("saveProjectSkill").textContent = "Saved";
  });
}

function activateProjectTab(name) {
  document.querySelectorAll(".project-tab").forEach((tab) => tab.classList.toggle("active", tab.dataset.projectTab === name));
  document.querySelectorAll(".project-page").forEach((page) => page.classList.remove("active"));
  $(`project${name[0].toUpperCase()}${name.slice(1)}Panel`)?.classList.add("active");
}

async function openProjectInEditor(startSession = false) {
  const path = state.projectArchive?.card?.workspace_path;
  if (!path) return;
  const result = await api("/api/workspace", { method: "POST", body: JSON.stringify({ path }) });
  if (!result.ok) throw new Error(result.message || "Could not open project");
  renderState(await api("/api/state"));
  if (startSession) renderState(await api("/api/clear", { method: "POST", body: JSON.stringify({}) }));
  activateTab("files");
  showWorkbench(); setActiveActivity("Agent"); $("promptInput").focus();
}

async function resumeProjectSession(sessionId) {
  renderState(await api("/api/memory/session/resume", { method: "POST", body: JSON.stringify({ session_id: sessionId }) }));
  showWorkbench(); setActiveActivity("Agent");
}

function renderMemory(memory) {
  const stats = memory.stats || {};
  $("persistentMemoryStats").textContent = `${stats.sessions || 0} sessions · ${stats.turns || 0} turns · ${stats.facts || 0} facts · ${stats.preferences || 0} preferences`;
  renderMemoryProjects(memory.projects || []);
  $("memoryFactsList").innerHTML = (memory.facts || []).map((item) => `
    <article class="memory-item" data-memory-id="${Number(item.id)}">
      <textarea class="memory-fact-input" spellcheck="false">${escapeHtml(item.fact)}</textarea>
      <div class="memory-item-actions">
        <button type="button" class="ghost memory-fact-save">Save</button>
        <button type="button" class="ghost memory-fact-delete">Delete</button>
      </div>
      <span class="memory-item-source">${escapeHtml(item.source || "manual")}</span>
    </article>
  `).join("") || `<div class="memory-item-source">No project facts have been saved.</div>`;
  $("memoryPreferencesList").innerHTML = Object.entries(memory.preferences || {}).map(([key, value]) => `
    <article class="memory-item" data-preference-key="${encodeURIComponent(key)}">
      <div><strong>${escapeHtml(key)}</strong><div class="memory-pref-value">${escapeHtml(value)}</div></div>
      <div class="memory-item-actions"><button type="button" class="ghost memory-preference-delete">Delete</button></div>
    </article>
  `).join("") || `<div class="memory-item-source">No preferences have been saved.</div>`;

  document.querySelectorAll(".memory-fact-save").forEach((button) => button.addEventListener("click", async () => {
    const item = button.closest(".memory-item");
    const id = Number(item.dataset.memoryId);
    const existing = (state.data?.memory?.persistent?.facts || []).find((fact) => Number(fact.id) === id);
    const memoryData = await api("/api/memory/fact", { method: "POST", body: JSON.stringify({ id, fact: item.querySelector("textarea").value, source: existing?.source || "manual" }) });
    state.data.memory.persistent = memoryData;
    renderMemory(memoryData);
  }));
  document.querySelectorAll(".memory-fact-delete").forEach((button) => button.addEventListener("click", async () => {
    const id = Number(button.closest(".memory-item").dataset.memoryId);
    const memoryData = await api("/api/memory/fact/delete", { method: "POST", body: JSON.stringify({ id }) });
    state.data.memory.persistent = memoryData;
    renderMemory(memoryData);
  }));
  document.querySelectorAll(".memory-preference-delete").forEach((button) => button.addEventListener("click", async () => {
    const key = decodeURIComponent(button.closest(".memory-item").dataset.preferenceKey);
    const memoryData = await api("/api/memory/preference/delete", { method: "POST", body: JSON.stringify({ key }) });
    state.data.memory.persistent = memoryData;
    renderMemory(memoryData);
  }));
}

function renderMemoryProjects(projects) {
  $("memoryProjectsList").innerHTML = projects.map((project) => `
    <button type="button" class="archive-entry memory-project" data-project-id="${Number(project.id)}">
      <strong>${escapeHtml(project.name)}</strong><span>${Number(project.sessions || 0)} sessions</span>
      <small>${escapeHtml(project.workspace_path)}</small>
    </button>
  `).join("") || `<div class="memory-item-source">No archived projects.</div>`;
  document.querySelectorAll(".memory-project").forEach((button) => button.addEventListener("click", async () => {
    document.querySelectorAll(".memory-project").forEach((item) => item.classList.toggle("selected", item === button));
    const archive = await api("/api/memory/archive", { method: "POST", body: JSON.stringify({ project_id: Number(button.dataset.projectId) }) });
    state.memoryArchiveProjectId = Number(button.dataset.projectId);
    renderMemorySessions(archive.sessions || []);
    renderMemoryArchiveProject(archive);
  }));
}

function renderMemoryArchiveProject(archive) {
  const project = archive.project || {};
  $("memoryArchiveProjectMeta").innerHTML = `<strong>${escapeHtml(project.name || "Unknown project")}</strong><span>${escapeHtml(project.workspace_path || "")}</span>`;
  $("memoryArchiveFiles").innerHTML = (archive.files || []).map((file) => `
    <button type="button" class="archive-file" data-path="${escapeHtml(file.path)}">
      <span>${escapeHtml(file.path)}</span><small>${formatSize(file.size || 0)}</small>
    </button>
  `).join("") || `<div class="memory-item-source">No readable files found at the archived path.</div>`;
  const facts = (archive.facts || []).map((item) => `<li>${escapeHtml(item.fact)}<small>${escapeHtml(item.source || "memory")}</small></li>`).join("");
  const preferences = Object.entries(archive.preferences || {}).map(([key, value]) => `<li><strong>${escapeHtml(key)}</strong>: ${escapeHtml(value)}</li>`).join("");
  $("memoryArchiveKnowledge").innerHTML = `
    <h4>Semantic facts</h4><ul>${facts || "<li>No saved facts</li>"}</ul>
    <h4>Preferences</h4><ul>${preferences || "<li>No saved preferences</li>"}</ul>
  `;
  document.querySelectorAll(".archive-file").forEach((button) => button.addEventListener("click", () => loadArchivedFile(button.dataset.path)));
}

async function loadArchivedFile(path) {
  if (!state.memoryArchiveProjectId) return;
  const data = await api("/api/memory/archive/file", {
    method: "POST",
    body: JSON.stringify({ project_id: state.memoryArchiveProjectId, path }),
  });
  setCodeEditorContent(
    data.path,
    `${data.ext} · archived project · ${formatSize(data.size)} · read-only preview`,
    data.content,
    data.ext || "txt"
  );
}

function renderMemorySessions(sessions) {
  $("memorySessionsList").innerHTML = sessions.map((session) => `
    <button type="button" class="archive-entry memory-session" data-session-id="${escapeHtml(session.id)}">
      <strong>${escapeHtml(session.title || "New session")}</strong><span>${Number(session.turns || 0)} turns</span>
    </button>
  `).join("") || `<div class="memory-item-source">No sessions in this project.</div>`;
  $("memorySessionPreview").textContent = "Select a session to preview its conversation.";
  $("resumeMemorySession").disabled = true;
  document.querySelectorAll(".memory-session").forEach((button) => button.addEventListener("click", async () => {
    document.querySelectorAll(".memory-session").forEach((item) => item.classList.toggle("selected", item === button));
    const archive = await api("/api/memory/archive", { method: "POST", body: JSON.stringify({ session_id: button.dataset.sessionId }) });
    const session = archive.session;
    $("memorySessionPreview").innerHTML = (session?.turns || []).map((turn) => `<div><strong>${escapeHtml(turn.role)}</strong><p>${escapeHtml(turn.content)}</p></div>`).join("") || "This session is empty.";
    $("resumeMemorySession").dataset.sessionId = button.dataset.sessionId;
    $("resumeMemorySession").disabled = false;
  }));
}

async function resumeMemorySession() {
  const sessionId = $("resumeMemorySession").dataset.sessionId;
  if (!sessionId) return;
  renderState(await api("/api/memory/session/resume", { method: "POST", body: JSON.stringify({ session_id: sessionId }) }));
}

async function addMemoryFact() {
  const fact = $("newMemoryFact").value.trim();
  if (!fact) return;
  const memory = await api("/api/memory/fact", { method: "POST", body: JSON.stringify({ fact, source: "manual" }) });
  $("newMemoryFact").value = "";
  state.data.memory.persistent = memory;
  renderMemory(memory);
}

async function addMemoryPreference() {
  const key = $("newPreferenceKey").value.trim();
  const value = $("newPreferenceValue").value.trim();
  if (!key || !value) return;
  const memory = await api("/api/memory/preference", { method: "POST", body: JSON.stringify({ key, value }) });
  $("newPreferenceKey").value = "";
  $("newPreferenceValue").value = "";
  state.data.memory.persistent = memory;
  renderMemory(memory);
}

async function forgetProjectMemory() {
  if (!window.confirm("Forget all conversations, project facts, and preferences stored for this workspace?")) return;
  renderState(await api("/api/memory/forget", { method: "POST", body: JSON.stringify({ confirm: true }) }));
}

function renderGit(git) {
  const notice = $("gitRepoNotice");
  const status = $("gitStatusFiles");
  const history = $("gitHistoryList");
  if (!git.is_repo) {
    notice.innerHTML = `<span>This workspace is not a Git repository.</span><button id="initGitRepo" type="button" class="primary">Initialize Git</button>`;
    status.innerHTML = "";
    history.innerHTML = "";
    $("initGitRepo").addEventListener("click", initGitRepo);
    $("pushGitChanges").disabled = true;
    return;
  }
  if (git.remote) $("gitRemoteUrl").value = git.remote;
  $("pushGitChanges").disabled = !git.remote;
  notice.innerHTML = `<span>Branch: <code>${escapeHtml(git.branch || "HEAD")}</code>${git.clean ? " · clean" : " · uncommitted changes"}</span>`;
  status.textContent = (git.files || []).map((file) => `${file.status}  ${file.path}`).join("\n");
  history.innerHTML = (git.history || []).map((commit) => `
    <article class="git-commit">
      <strong>${escapeHtml(commit.message)}</strong>
      <button type="button" class="ghost git-revert" data-hash="${escapeHtml(commit.hash)}">Revert</button>
      <span>${escapeHtml(commit.short_hash)} · ${escapeHtml(commit.author)} · ${escapeHtml(commit.date)}</span>
    </article>
  `).join("") || `<div class="git-repo-notice">No commits yet.</div>`;
  document.querySelectorAll(".git-revert").forEach((button) => {
    button.addEventListener("click", () => revertGitCommit(button.dataset.hash));
  });
}

function gitCredentials() {
  const usePat = $("gitAuthMode").value === "pat";
  return {
    username: usePat ? $("gitUsername").value.trim() : "",
    token: usePat ? $("gitToken").value : "",
  };
}

function updateGitAuthPanel() {
  $("gitAuthMode").parentElement.parentElement.classList.toggle("show-pat", $("gitAuthMode").value === "pat");
}

function appendGitTerminal(line) {
  const terminal = $("gitCloneTerminal");
  terminal.classList.add("active");
  terminal.textContent += `${line}\n`;
  terminal.scrollTop = terminal.scrollHeight;
}

async function cloneGitRepository() {
  const remoteUrl = $("gitRemoteUrl").value.trim();
  if (!remoteUrl) {
    $("gitRemoteUrl").focus();
    return;
  }
  const terminal = $("gitCloneTerminal");
  terminal.textContent = "";
  setLoading(true, "Cloning repository...");
  $("cloneGitRepo").disabled = true;
  try {
    const response = await fetch("/api/git/clone_stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        remote_url: remoteUrl,
        destination: $("gitCloneDestination").value.trim(),
        ...gitCredentials(),
      }),
    });
    if (!response.ok || !response.body) {
      const error = await response.json().catch(() => ({ error: "Clone request failed" }));
      throw new Error(error.error || "Clone request failed");
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const line of lines) {
        if (!line.trim()) continue;
        const event = JSON.parse(line);
        if (event.type === "git_clone_output") appendGitTerminal(event.content);
        else if (event.type === "git_clone_status") appendGitTerminal(event.message);
        else if (event.type === "git_clone_error") throw new Error(event.message);
        else if (event.type === "git_clone_done") {
          appendGitTerminal(`Clone completed: ${event.path}`);
          renderState(event.state);
          showEditorView("git");
        }
      }
    }
  } catch (error) {
    appendGitTerminal(`ERROR: ${error.message}`);
  } finally {
    $("gitToken").value = "";
    $("cloneGitRepo").disabled = false;
    setLoading(false);
  }
}

async function previewGitPush() {
  const preview = await api("/api/git/push-preview", { method: "POST", body: JSON.stringify({}) });
  const commitLines = (preview.commits || []).map((commit) => `${commit.hash}  ${commit.message}`);
  state.pendingPush = { ...gitCredentials(), preview };
  state.pendingApprovalType = "git-push";
  $("approvalTitle").textContent = "Push Changes to Remote";
  $("approvalToolName").textContent = `git push origin ${preview.branch}`;
  $("approvalWorkspace").textContent = preview.remote;
  $("approvalPreviewLabel").textContent = `${preview.ahead || commitLines.length} commit(s) will be pushed`;
  $("approvalPreview").classList.remove("diff-preview");
  $("approvalPreview").textContent = commitLines.join("\n") || "The current branch will be pushed to its remote.";
  $("approvalAlways").parentElement.style.display = "none";
  $("approvalApprove").textContent = "Approve and push";
  $("approvalModal").style.display = "grid";
}

async function initGitRepo() {
  if (!window.confirm("Initialize a Git repository in this workspace?")) return;
  const git = await api("/api/git/init", { method: "POST", body: JSON.stringify({}) });
  state.data.git = git;
  renderGit(git);
}

async function revertGitCommit(hash) {
  if (!window.confirm(`Create a revert commit for ${hash.slice(0, 8)}?`)) return;
  const result = await api(`/api/git/revert/${encodeURIComponent(hash)}`, { method: "POST", body: JSON.stringify({}) });
  state.data.git = result.git;
  renderGit(result.git);
  await refresh();
}

function showEditorView(name) {
  const isGit = name === "git";
  $("codeEditorWrap").classList.toggle("active", !isGit);
  $("gitHistoryView").classList.toggle("active", isGit);
  $("showCodeTab").classList.toggle("active", !isGit);
  $("showGitTab").classList.toggle("active", isGit);
}

function renderDiffPreview(diff) {
  return String(diff || "").split("\n").map((line) => {
    let kind = "";
    if (line.startsWith("+++") || line.startsWith("---") || line.startsWith("@@")) kind = "meta";
    else if (line.startsWith("+")) kind = "add";
    else if (line.startsWith("-")) kind = "remove";
    return `<span class="diff-line ${kind}">${escapeHtml(line) || " "}</span>`;
  }).join("");
}

function showApproval(event, isGitDiff = false) {
  state.pendingApprovalType = isGitDiff ? "git" : "tool";
  $("approvalTitle").textContent = isGitDiff ? "Review File Change" : "Execution Approval Required";
  $("approvalToolName").textContent = event.name || "tool";
  $("approvalWorkspace").textContent = state.data?.workspace?.path || "";
  $("approvalPreviewLabel").textContent = isGitDiff ? "Proposed file diff" : "Command / Code preview";
  $("approvalPreview").classList.toggle("diff-preview", isGitDiff);
  if (isGitDiff) $("approvalPreview").innerHTML = renderDiffPreview(event.preview);
  else $("approvalPreview").textContent = event.preview || "";
  $("approvalAlways").checked = false;
  $("approvalAlways").parentElement.style.display = "flex";
  $("approvalApprove").textContent = "Approve and run";
  $("approvalModal").style.display = "grid";
}

async function resolveApproval(approved) {
  if (state.pendingApprovalType === "git-push") {
    try {
      if (approved) {
        const result = await api("/api/git/push", {
          method: "POST",
          body: JSON.stringify({ approved: true, username: state.pendingPush?.username || "", token: state.pendingPush?.token || "" }),
        });
        state.data.git = result.git;
        renderGit(result.git);
        $("gitConnectionStatus").textContent = result.message || "Push completed";
      }
    } finally {
      $("gitToken").value = "";
      state.pendingPush = null;
      state.pendingApprovalType = null;
      $("approvalModal").style.display = "none";
    }
    return;
  }
  const prefix = state.pendingApprovalType === "git" ? "/api/git" : "/api/approval";
  const endpoint = approved ? "approve" : "reject";
  await api(`${prefix}/${endpoint}`, {
    method: "POST",
    body: JSON.stringify(approved ? { always_allow_for_session: $("approvalAlways").checked } : { reason: "Rejected by user" }),
  });
  $("approvalModal").style.display = "none";
  state.pendingApprovalType = null;
}

function estimateTextTokens(text) {
  return Math.max(0, Math.ceil(String(text || "").length / 4));
}

function updateTokenUsage() {
  renderTokenUsage(state.contextUsage || {});
}

function renderTokenUsage(usage) {
  const activeContextTokens = state.activeFile && state.fileContent ? estimateTextTokens(state.fileContent) : 0;
  const draftPromptTokens = $("promptInput") ? estimateTextTokens($("promptInput").value) : 0;
  const extraTokens = activeContextTokens + draftPromptTokens;
  const inputTokens = Number(usage.input_tokens || 0) + extraTokens;
  const settingsBudget = Number(state.data?.settings?.context_token_budget || 0);
  const effectiveWindow = Number(usage.effective_window || usage.context_window || settingsBudget || 0);
  const contextWindow = Number(usage.context_window || effectiveWindow);
  const configuredBudget = Number(usage.configured_budget || settingsBudget || effectiveWindow);
  const percent = effectiveWindow ? Math.min(999, Math.round((inputTokens / effectiveWindow) * 100)) : 0;
  const fillPercent = Math.max(0, Math.min(100, percent));
  const meter = $("tokenMeter");
  meter.classList.toggle("warn", percent >= 70 && percent < 90);
  meter.classList.toggle("danger", percent >= 90);
  $("tokenPercent").textContent = `${percent}%`;
  $("tokenBarFill").style.width = `${fillPercent}%`;
  $("tokenDetails").textContent = `${formatTokens(inputTokens)} / ${formatTokens(effectiveWindow)} tokens`;

  const source = usage.window_source || "estimated";
  const counter = usage.counter || "estimated";
  const remaining = Math.max(0, effectiveWindow - inputTokens);
  meter.title = [
    `Input tokens: ${inputTokens.toLocaleString()}`,
    `Base context tokens: ${Number(usage.input_tokens || 0).toLocaleString()}`,
    `Active editor estimate: ${activeContextTokens.toLocaleString()}`,
    `Draft prompt estimate: ${draftPromptTokens.toLocaleString()}`,
    `Effective context budget: ${effectiveWindow.toLocaleString()}`,
    `Model context window: ${contextWindow.toLocaleString()} (${source})`,
    `Configured context budget: ${configuredBudget.toLocaleString()}`,
    `Reserved response tokens: ${Number(usage.response_budget || 0).toLocaleString()}`,
    `Remaining input tokens: ${remaining.toLocaleString()}`,
    `Counter: ${counter}`,
  ].join("\n");
}

function renderModels(modelPayload, activeModel) {
  const models = modelPayload.models || [];
  const selectedModel = modelPayload.selected_model || activeModel;
  const select = $("modelSelect");
  const options = models.length ? models : [selectedModel || "llama3"];
  select.innerHTML = options.map((name) => `
    <option value="${escapeHtml(name)}" ${name === selectedModel ? "selected" : ""}>${escapeHtml(name)}</option>
  `).join("");
  select.title = modelPayload.error ? `Model refresh error: ${modelPayload.error}` : "Model";
}

function renderFiles() {
  const query = $("fileSearch").value.toLowerCase();
  const files = (state.data?.workspace.files || []).filter((f) =>
    f.path.toLowerCase().includes(query)
  );
  $("fileList").innerHTML = files.map((file) => `
    <button class="file-item ${state.activeFile === file.path ? "active" : ""}" data-path="${escapeHtml(file.path)}">
      ${escapeHtml(file.path)}
    </button>
  `).join("");
  document.querySelectorAll(".file-item").forEach((btn) => {
    btn.addEventListener("click", () => loadFile(btn.dataset.path));
  });
  refreshSchematicGraph();
}

function renderSkills() {
  const usage = new Map((state.data?.skill_usage?.skills || []).map((item) => [item.name, item]));
  $("skillsList").innerHTML = (state.data?.skills || []).map((skill) => `
    <button class="skill-item skill-mode-${usage.get(skill.name)?.mode || "auto"}" data-skill="${escapeHtml(skill.name)}" ${skill.disabled ? "disabled" : ""}>
      /${escapeHtml(skill.name)}
      <span class="skill-mode-label">${usage.get(skill.name)?.mode === "pinned" ? "Pinned" : usage.get(skill.name)?.mode === "off" ? "Off" : "Auto"}</span>
      <span class="skill-desc">${escapeHtml(skill.description || skill.category)} · ${usage.get(skill.name)?.project_uses || 0} uses${usage.get(skill.name)?.project_uses ? "" : " ⚠"}</span>
    </button>
  `).join("");
  renderRoutingNotice("skillsRoutingNotice", state.data?.skill_usage?.routing || {});
  $("skillsRecentUsage").innerHTML = (state.data?.skill_usage?.recent || []).slice(0, 20).map((event) => `<div class="skill-usage-row"><strong>/${escapeHtml(event.skill_name)}</strong><span>${escapeHtml(event.status)} · ${formatRelativeTime(event.timestamp)} · session ${escapeHtml(event.session_id.slice(0, 6))}</span></div>`).join("") || `<div class="memory-item-source">No skill usage recorded for this project.</div>`;
  document.querySelectorAll(".skill-item").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const current = usage.get(btn.dataset.skill)?.mode || "auto";
      const next = current === "auto" ? "pinned" : current === "pinned" ? "off" : "auto";
      renderState(await api("/api/skills/mode", {
        method: "POST",
        body: JSON.stringify({ skill_name: btn.dataset.skill, mode: next }),
      }));
    });
  });
}

function renderPrompts() {
  const query = $("promptSearch").value.toLowerCase();
  const selected = state.data?.settings.selected_prompt;
  const prompts = (state.data?.prompts?.prompts || []).filter((prompt) =>
    prompt.name.toLowerCase().includes(query) ||
    prompt.category.toLowerCase().includes(query) ||
    prompt.preview.toLowerCase().includes(query)
  );
  $("promptsList").innerHTML = prompts.map((prompt) => `
    <button class="prompt-item ${selected === prompt.name ? "selected" : ""}" data-prompt="${escapeHtml(prompt.name)}">
      ${escapeHtml(prompt.name)}
      <span class="prompt-meta">${escapeHtml(prompt.category)} · ${Math.floor(prompt.size / 1000)}k · ${escapeHtml(prompt.preview)}</span>
    </button>
  `).join("");
  document.querySelectorAll(".prompt-item").forEach((btn) => {
    btn.addEventListener("click", async () => selectPrompt(btn.dataset.prompt));
  });
}

function isRTL(text) {
  const trimmed = String(text || "").trim();
  if (!trimmed) return false;
  // Decimal digits are not direction votes, regardless of their script.
  const clean = trimmed.replace(/[\p{Decimal_Number}\s.,!?:;"'()\[\]{}<>\/\\@#$%^&*_+=~`|-]/gu, "");
  if (!clean) return false;
  const rtlChars = clean.match(/[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]/g) || [];
  return (rtlChars.length / clean.length) > 0.2;
}

function renderMessages() {
  const messages = state.data?.messages || [];
  const toolsLog = state.data?.tools_log || [];
  const currentSession = state.data?.memory?.persistent?.session_id;
  const skillEvents = (state.data?.skill_usage?.recent || []).filter((event) => event.session_id === currentSession);
  $("messages").innerHTML = messages.map((msg, index) => {
    const assistantIndex = messages.slice(0, index + 1).filter((m) => m.role === "assistant").length - 1;
    const tools = msg.role === "assistant" && toolsLog[assistantIndex] ? toolsLog[assistantIndex] : [];
    const turnEvents = msg.role === "assistant" ? skillEvents.filter((event) => event.turn_index === assistantIndex + 1 && ["selected", "applied", "failed"].includes(event.status)) : [];
    const skillHtml = turnEvents.map((event) => `<div class="skill-event-box ${event.status === "failed" ? "failed" : ""}"><strong>${event.status === "selected" ? "Using skill" : event.status === "applied" ? "Skill applied" : "Skill failed"}: /${escapeHtml(event.skill_name)}</strong><span>${event.matched_keywords?.length ? `matched: ${event.matched_keywords.map((word) => `&quot;${escapeHtml(word)}&quot;`).join(", ")}` : escapeHtml(event.triggered_by)}</span></div>`).join("");
    const toolHtml = tools.length ? `<div class="tool-box">${escapeHtml(tools.map((t) =>
      `${t.name}(${JSON.stringify(t.args || {})})\n${String(t.result || "").slice(0, 1200)}`
    ).join("\n\n"))}</div>` : "";
    const isMsgRTL = isRTL(msg.content);
    const dirAttr = isMsgRTL ? "rtl" : "ltr";
    return `
      <article class="message ${msg.role} ${dirAttr}" dir="${dirAttr}">
        <span class="role">${msg.role}</span>
        ${skillHtml}
        ${renderMessageContent(msg)}
        ${toolHtml}
      </article>
    `;
  }).join("");
  $("messages").scrollTop = $("messages").scrollHeight;
}

function renderMessageContent(msg) {
  const content = msg.content || "";
  if (msg.role !== "assistant") return escapeHtml(content);
  const blocks = extractCodeBlocks(content);
  if (!blocks.length) return escapeHtml(content);
  const prose = content.replace(/```([^\n`]*)\n([\s\S]*?)```/g, "").trim();
  const note = `<div class="tool-box">Code artifact updated in Editor · ${blocks.length} block${blocks.length > 1 ? "s" : ""}</div>`;
  return `${escapeHtml(prose)}${prose ? "\n" : ""}${note}`;
}

function extractCodeBlocks(text, includeOpenBlock = false) {
  const blocks = [];
  const re = /```([^\n`]*)\n([\s\S]*?)```/g;
  let match;
  let lastEnd = 0;
  while ((match = re.exec(text || "")) !== null) {
    const info = (match[1] || "text").trim();
    const code = (match[2] || "").trimEnd();
    lastEnd = re.lastIndex;
    if (code.trim()) {
      blocks.push({ info, code });
    }
  }
  if (includeOpenBlock) {
    const remaining = String(text || "").slice(lastEnd);
    const open = remaining.match(/```([^\n`]*)\n([\s\S]*)$/);
    if (open) {
      const info = (open[1] || "text").trim();
      const code = (open[2] || "").trimEnd();
      if (code.trim()) {
        blocks.push({ info, code });
      }
    }
  }
  return blocks;
}

function pickBestCodeBlock(blocks) {
  if (!blocks.length) return null;
  return blocks.reduce((best, block) => (
    block.code.length >= best.code.length ? block : best
  ), blocks[0]);
}

function looksLikeCode(text) {
  const value = String(text || "").trim();
  if (!value) return false;
  const codeMarkers = [
    /(^|\n)\s*(import|from|def|class|function|const|let|var|return|async|await)\b/,
    /(^|\n)\s*(if|for|while|try|catch|switch)\s*[\(\w]/,
    /<\/?[a-z][\s\S]*>/i,
    /[{;}]\s*$/,
    /(^|\n)\s*#include\b/,
    /(^|\n)\s*(public|private|protected)\s+(class|static|void|int|string)\b/i,
  ];
  return codeMarkers.some((pattern) => pattern.test(value));
}

function inferCodeBlockFromText(text) {
  const value = String(text || "").trim();
  if (!looksLikeCode(value)) return null;
  let info = "txt";
  if (/(^|\n)\s*(from|import|def|class)\b/.test(value)) info = "python";
  else if (/<\/?[a-z][\s\S]*>/i.test(value)) info = "html";
  else if (/(^|\n)\s*(function|const|let|var|export|import)\b/.test(value)) info = "javascript";
  else if (/(^|\n)\s*(public|private|protected)\s+(class|static|void|int|string)\b/i.test(value)) info = "java";
  else if (/(^|\n)\s*[.#]?[a-z0-9_-]+\s*\{/.test(value)) info = "css";
  return { info, code: value };
}

function setGeneratedCodeFromText(text, metaPrefix = "extracted from latest agent response", force = false) {
  if (!force && state.activeFile && state.activeFile !== "Generated Code") return false;
  if (state.editorDirty) return false;
  const blocks = extractCodeBlocks(text, true);
  const block = blocks.length ? pickBestCodeBlock(blocks) : (force ? inferCodeBlockFromText(text) : null);
  if (!block) return false;
  setCodePreview(
    "Generated Code",
    `${block.info || "text"} · ${block.code.length.toLocaleString()} chars · ${metaPrefix}`,
    block.code,
    block.info || "txt"
  );
  return true;
}

function renderGeneratedArtifactFromState(force = false) {
  const artifact = state.data?.generated_artifact;
  if (!artifact?.content) return false;
  if (!force && state.activeFile && state.activeFile !== "Generated Code") return false;
  if (state.editorDirty) return false;
  setCodePreview(
    artifact.title || "Generated Code",
    `${artifact.info || "text"} · ${artifact.content.length.toLocaleString()} chars · ${artifact.source || "agent artifact"}`,
    artifact.content,
    artifact.info || "txt"
  );
  return true;
}

function renderGeneratedCodeFromMessages(force = false) {
  if (!force && state.activeFile && state.activeFile !== "Generated Code") return;
  if (state.editorDirty) return;
  const messages = state.data?.messages || [];
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    if (messages[i].role !== "assistant") continue;
    if (setGeneratedCodeFromText(messages[i].content, "extracted from latest agent response", force)) return;
  }
}

function setWorkspaceLocked(isLocked) {
  state.workspaceLocked = false;
  document.body.classList.remove("workspace-locked");
}

function setLoading(isLoading, text = "Working...") {
  document.body.classList.toggle("loading", isLoading);
  $("loadingText").textContent = text;
  const agentLabel = document.querySelector(".signal.is-agent .signal-label");
  if (agentLabel) agentLabel.textContent = isLoading ? "Agent working" : "Agent idle";
}

function appendStreamingAssistant() {
  const article = document.createElement("article");
  article.className = "message assistant streaming";
  article.innerHTML = `<span class="role">assistant</span><span class="stream-content"></span>`;
  $("messages").appendChild(article);
  $("messages").scrollTop = $("messages").scrollHeight;
  return article.querySelector(".stream-content");
}

function appendToolStatus(name, text) {
  const article = document.createElement("article");
  article.className = "message assistant";
  article.innerHTML = `<span class="role">tool</span><div class="tool-box">${escapeHtml(`${name}\n${text}`)}</div>`;
  $("messages").appendChild(article);
  $("messages").scrollTop = $("messages").scrollHeight;
}

function updateGeneratedCodeFromStreaming(text) {
  setGeneratedCodeFromText(text, "live stream", true);
}

async function loadFile(path) {
  const data = await api(`/api/file?path=${encodeURIComponent(path)}`);
  setCodeEditorContent(
    path,
    `${data.ext} · ${formatSize(data.size)} · ${data.content.length.toLocaleString()} chars · editable`,
    data.content,
    data.ext || "txt"
  );
  renderFiles();
}

function downloadCurrentCode() {
  if (!state.fileContent) return;
  const ext = extensionForInfo(state.generatedInfo);
  const baseName = state.activeFile && state.activeFile !== "Generated Code"
    ? state.activeFile.split(/[\\/]/).pop()
    : `generated-code.${ext}`;
  const filename = baseName.includes(".") ? baseName : `${baseName}.${ext}`;
  const blob = new Blob([state.fileContent], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function currentActiveContext() {
  if (!state.activeFile || !state.fileContent) return null;
  return {
    path: state.activeFile,
    content: state.fileContent,
    info: state.generatedInfo || "txt",
  };
}

async function refresh() {
  renderState(await api("/api/state"));
  await showProjects();
}

function renderCodeIndex(index = {}) {
  $("indexFileCount").textContent = Number(index.files || 0).toLocaleString();
  $("indexSymbolCount").textContent = Number(index.symbols || 0).toLocaleString();
  $("indexChunkCount").textContent = Number(index.chunks || 0).toLocaleString();
  const hasIndex = Number(index.files || 0) > 0;
  const fresh = index.up_to_date;
  $("indexFreshness").textContent = !hasIndex ? "Not indexed" : fresh === false ? "Changes detected" : fresh === true ? "Up to date" : "Ready";
  $("indexLastRun").textContent = index.last_indexed ? formatRelativeTime(index.last_indexed) : "Never";
  $("indexEmbeddingModel").textContent = index.embedding_model || "nomic-embed-text";
  $("indexVectorBackend").textContent = index.vector_backend === "chromadb" ? "Advanced semantic search" : "Local fallback search";
  $("indexStatusDot").className = hasIndex && fresh !== false ? "ready" : hasIndex ? "stale" : "";
  const embeddingError = index.embedding_error || "";
  const notice = embeddingError
    ? friendlyErrorMessage(embeddingError)
    : "";
  $("indexError").textContent = notice;
  $("indexError").classList.toggle("visible", Boolean(notice));
  if (index.project_summary) $("indexProjectSummary").textContent = index.project_summary;
  $("indexGraphStats").textContent = `${Number(index.graph_nodes || 0)} files · ${Number(index.graph_edges || 0)} relations`;
}

function renderProjectIntelligence(payload = {}) {
  const overview = payload.overview || {};
  $("indexProjectSummary").textContent = overview.summary || "Build the index to generate a project-level architecture summary.";
  $("indexGraphStats").textContent = `${Number(overview.nodes || 0)} files · ${Number(overview.edges || 0)} relations`;
  $("indexEntryPoints").innerHTML = (overview.entry_points || []).map((path) => `<code title="${escapeHtml(path)}">${escapeHtml(path)}</code>`).join("");
  const lines = [];
  (payload.graph || []).forEach((node) => {
    lines.push(`▾ ${node.file_path}`);
    (node.related || []).forEach((edge) => lines.push(`   ${edge.relation_type} → ${edge.to_file}  [${edge.detail}]`));
  });
  $("indexDependencyTree").textContent = lines.join("\n") || "No resolved project dependencies yet.";
}

async function refreshCodeIndex() {
  const [index, intelligence] = await Promise.all([api("/api/index"), api("/api/index/overview")]);
  if (state.data) state.data.code_index = index;
  renderCodeIndex(index);
  renderProjectIntelligence(intelligence);
}

async function runCodeIndex(path, label) {
  setLoading(true, label, false);
  $("syncCodeIndex").disabled = true;
  $("rebuildCodeIndex").disabled = true;
  try {
    const index = await api(path, { method: "POST", body: "{}" });
    if (state.data) state.data.code_index = index;
    renderCodeIndex(index);
    await refreshCodeIndex();
  } catch (err) {
    $("indexError").textContent = friendlyErrorMessage(err.message);
    $("indexError").classList.add("visible");
  } finally {
    $("syncCodeIndex").disabled = false;
    $("rebuildCodeIndex").disabled = false;
    setLoading(false);
  }
}

function activateFileView(name) {
  document.querySelectorAll(".file-view-tab").forEach((button) => button.classList.toggle("active", button.dataset.fileView === name));
  $("fileBrowserView").classList.toggle("active", name === "browser");
  $("codeIndexView").classList.toggle("active", name === "index");
  if (name === "index") refreshCodeIndex().catch((err) => {
    $("indexError").textContent = friendlyErrorMessage(err.message);
    $("indexError").classList.add("visible");
  });
}

function renderRoutingNotice(id, routing) {
  const skipped = routing.skipped || [];
  const details = [];
  if (skipped.length) details.push(`${skipped.length} matched skill(s) skipped by the ${routing.limit || 3}-skill context limit: ${skipped.join(", ")}`);
  if (routing.confirmation_used) details.push("Smart LLM confirmation was used");
  if (routing.selected?.length) details.push(`Active: ${routing.selected.join(", ")}`);
  $(id).textContent = details.join(" · ");
  $(id).classList.toggle("visible", details.length > 0);
}

function appendSkillStatus(event) {
  const article = document.createElement("article");
  article.className = `message assistant skill-event ${event.type === "skill_failed" ? "failed" : ""}`;
  const keywords = (event.matched_keywords || []).map((word) => `"${word}"`).join(", ");
  const title = event.type === "skill_applied" ? "Skill applied" : event.type === "skill_failed" ? "Skill failed" : "Using skill";
  article.innerHTML = `<span class="role">skill</span><div class="skill-event-box"><strong>${title}: /${escapeHtml(event.skill)}</strong><span>${escapeHtml(event.reason || (keywords ? `matched: ${keywords}` : ""))}</span></div>`;
  $("messages").appendChild(article);
  $("messages").scrollTop = $("messages").scrollHeight;
}

async function openWorkspace() {
  const data = await api("/api/workspace", {
    method: "POST",
    body: JSON.stringify({ path: $("workspaceInput").value.trim() }),
  });
  renderState(data);
}

async function browseWorkspace() {
  setLoading(true, "Opening folder picker...");
  try {
    const data = await api("/api/browse", {
      method: "POST",
      body: JSON.stringify({ initial_dir: $("workspaceInput").value.trim() }),
    });
    if (data.cancelled) return;
    $("workspaceInput").value = data.path || data.workspace?.path || $("workspaceInput").value;
    renderState(await api("/api/state"));
  } catch (err) {
    alert(err.message || "Could not open the folder picker");
  } finally {
    setLoading(false);
  }
}

function updateCustomApiPanel() {
  $("customApiPanel").classList.toggle("open", $("connMode").value === "🔑 Custom API");
}

function updateTavilyPanel(settings = state.data?.settings || {}) {
  const enabled = $("tavilyEnabled").checked;
  $("tavilyKeyRow").classList.toggle("disabled-row", !enabled);
  $("tavilyApiKey").disabled = !enabled;
  $("tavilyStatus").textContent = enabled
    ? (settings.tavily_key_set ? "Tavily is enabled · key saved" : "Tavily is enabled · add API key")
    : "Tavily is disabled";
}

async function saveSettings() {
  const apiUrl = $("topCustomApiUrl").value.trim() || $("customApiUrl").value.trim() || "https://api.openai.com/v1";
  const apiKey = $("topCustomApiKey").value || $("customApiKey").value;
  const customApiModel = $("topCustomApiModel").value.trim() || $("customApiModel").value.trim() || "gpt-4o-mini";
  renderState(await api("/api/settings", {
    method: "POST",
    body: JSON.stringify({
      conn_mode: $("connMode").value,
      model: $("modelSelect").value,
      temperature: Number($("temperature").value),
      enable_thinking: $("thinking").checked,
      auto_continue: $("autoContinue").checked,
      memory_enabled: $("memoryEnabled").checked,
      context_token_budget: Number($("contextTokenBudget").value),
      response_token_budget: Number($("responseTokenBudget").value),
      tavily_enabled: $("tavilyEnabled").checked,
      tavily_api_key: $("tavilyApiKey").value,
      git_approval_mode: $("gitApprovalMode").checked,
      smart_skill_confirmation: $("smartSkillConfirmation").checked,
      sandbox_mode: $("sandboxMode") ? $("sandboxMode").value : "auto",
      sandbox_docker_image: $("sandboxDockerImage") ? $("sandboxDockerImage").value.trim() : "python:3.11-slim",
      custom_api_url: apiUrl,
      custom_api_key: apiKey,
      custom_api_model: customApiModel,
    }),
  }));
}

async function compactMemory() {
  renderState(await api("/api/memory/compact", {
    method: "POST",
    body: JSON.stringify({}),
  }));
}

async function testSkills() {
  $("skillsStatus").textContent = "Testing...";
  const result = await api("/api/skills/diagnostics");
  const problems = []
    .concat(result.duplicates?.map((name) => `duplicate:${name}`) || [])
    .concat(result.missing_description?.map((name) => `missing desc:${name}`) || [])
    .concat(result.failed_slash_detection?.map((name) => `slash failed:${name}`) || [])
    .concat(result.selected_missing?.map((name) => `missing selected:${name}`) || []);
  $("skillsStatus").textContent = result.ok
    ? `OK · ${result.count} skills · auto prompt ${result.auto_select_prompt_chars} chars`
    : `Issues · ${problems.slice(0, 3).join(", ")}${problems.length > 3 ? "..." : ""}`;
}

async function refreshModels() {
  await saveSettings();
  renderState(await api("/api/state"));
}

async function selectPrompt(name) {
  const prompt = await api(`/api/prompt?name=${encodeURIComponent(name)}`);
  $("systemPromptEditor").value = prompt.content;
  $("selectedPromptName").textContent = prompt.name;
  renderState(await api("/api/prompt", {
    method: "POST",
    body: JSON.stringify({ selected_prompt: prompt.name }),
  }));
}

async function savePrompt() {
  renderState(await api("/api/prompt", {
    method: "POST",
    body: JSON.stringify({ system_prompt: $("systemPromptEditor").value }),
  }));
}

async function scanProject() {
  setLoading(true, "Scanning project...");
  try {
    const data = await api("/api/scan", { method: "POST", body: JSON.stringify({ max_files: 250 }) });
    renderState(data.state);
  } finally {
    setLoading(false);
  }
}

function dispatchStreamEvent(event, ctx) {
  if (!event || typeof event !== "object") return;
  if (event.type === "state") {
    renderState(event.state);
    ctx.ensureStreamTarget("Preparing context...");
  } else if (event.type === "status") {
    setLoading(true, event.message);
    ctx.ensureStreamTarget(event.message || "Working...");
  } else if (event.type === "token") {
    ctx.ensureStreamTarget("");
    ctx.appendToken(event.content || "");
  } else if (event.type === "tool_call") {
    setLoading(true, `Running ${event.name}...`);
    appendToolStatus(event.name, JSON.stringify(event.args || {}, null, 2));
  } else if (event.type === "tool_result") {
    appendToolStatus(`${event.name} result`, String(event.result || "").slice(0, 1200));
  } else if (event.type === "skill_selected" || event.type === "skill_applied" || event.type === "skill_failed") {
    appendSkillStatus(event);
  } else if (event.type === "approval_required") {
    setLoading(true, `Waiting for approval: ${event.name}`);
    showApproval(event, false);
  } else if (event.type === "git_diff_preview") {
    setLoading(true, `Reviewing changes to ${event.args?.path || "file"}`);
    showApproval(event, true);
    showEditorView("git");
  } else if (event.type === "git_commit_created") {
    appendToolStatus("Git checkpoint", `${event.commit.slice(0, 8)} ${event.message}`);
  } else if (event.type === "git_checkpoint_created") {
    appendToolStatus("Session checkpoint", `Created branch ${event.branch}`);
  } else if (event.type === "memory_used") {
    $("memoryUsageIndicator").textContent = `${event.count} memory fact(s) used`;
  } else if (event.type === "code_rag_used") {
    appendToolStatus("Codebase context", event.query_type === "project_level" ? "Project overview and dependency graph loaded" : `${event.count} relevant chunk(s) plus graph relations loaded`);
  } else if (event.type === "code_index_updated") {
    appendToolStatus("Code index", `${event.path || "File"} updated · ${event.chunks || 0} chunk(s)`);
  } else if (event.type === "code_index_error") {
    appendToolStatus("Code index warning", event.message || "Index update failed");
  } else if (event.type === "cancelled") {
    ctx.showStreamNotice("⛔ Generation stopped by user.");
    ctx.setSawDone(true);
  } else if (event.type === "error") {
    ctx.showStreamNotice(event.message || "Error");
  } else if (event.type === "done") {
    ctx.setSawDone(true);
    renderState(event.state);
  }
}

async function streamViaWebSocket(prompt, activeContext, ctx, controller) {
  if (typeof WebSocket === "undefined") throw new Error("WebSocket not supported");
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  const sid = getActiveSessionId();
  const wsUrl = `${protocol}//${location.host}/ws/chat?session_id=${encodeURIComponent(sid)}`;

  return new Promise((resolve, reject) => {
    let ws;
    try {
      ws = new WebSocket(wsUrl);
    } catch (e) {
      return reject(e);
    }

    let opened = false;
    let completed = false;

    const cleanup = () => {
      if (ws) {
        ws.onopen = null;
        ws.onmessage = null;
        ws.onerror = null;
        ws.onclose = null;
        try { ws.close(); } catch (_) {}
      }
    };

    const abortListener = () => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        try { ws.send(JSON.stringify({ type: "cancel", session_id: sid })); } catch (_) {}
      }
      cleanup();
      resolve(false);
    };
    controller.signal.addEventListener("abort", abortListener, { once: true });

    ws.onopen = () => {
      opened = true;
      try {
        ws.send(JSON.stringify({ type: "chat", session_id: sid, prompt, active_context: activeContext }));
      } catch (err) {
        cleanup();
        reject(err);
      }
    };

    ws.onmessage = async (event) => {
      try {
        const payload = JSON.parse(event.data);
        dispatchStreamEvent(payload, ctx);
        if (payload.type === "done" || payload.type === "cancelled") {
          completed = true;
          controller.signal.removeEventListener("abort", abortListener);
          cleanup();
          resolve(true);
        }
      } catch (err) {
        ctx.showStreamNotice(`[ws parse error] ${err.message}`);
      }
    };

    ws.onerror = (err) => {
      if (!opened) {
        cleanup();
        reject(new Error("WebSocket connection failed"));
      } else {
        ctx.showStreamNotice("[ws connection error]");
      }
    };

    ws.onclose = () => {
      controller.signal.removeEventListener("abort", abortListener);
      if (!completed && !opened) {
        reject(new Error("WebSocket closed before opening"));
      } else {
        resolve(completed);
      }
    };
  });
}

async function streamViaHttp(prompt, activeContext, ctx, controller) {
  const sid = getActiveSessionId();
  const res = await fetch("/api/chat_stream", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Session-ID": sid },
    body: JSON.stringify({ session_id: sid, prompt, active_context: activeContext }),
    signal: controller.signal,
  });
  if (!res.ok || !res.body) {
    const fallback = await res.json().catch(() => ({ error: "Streaming request failed" }));
    throw new Error(fallback.error || "Streaming request failed");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    for (const line of lines) {
      if (!line.trim()) continue;
      try {
        const event = JSON.parse(line);
        dispatchStreamEvent(event, ctx);
      } catch (err) {
        ctx.showStreamNotice(`[stream parse error] ${err.message}`);
      }
    }
  }
  if (buffer.trim()) {
    try {
      const event = JSON.parse(buffer.trim());
      dispatchStreamEvent(event, ctx);
    } catch (_) {}
  }
}

async function sendPrompt(prompt) {
  setLoading(true, "Sending prompt...");
  $("sendBtn").style.display = "none";
  $("stopBtn").style.display = "inline-flex";
  $("stopBtn").disabled = false;
  $("stopBtn").innerHTML = `<svg viewBox="0 0 24 24" fill="currentColor"><rect x="4" y="4" width="16" height="16" rx="2"/></svg> Stop`;

  let streamTarget = appendStreamingAssistant();
  streamTarget.textContent = "Preparing request...";
  let streamText = "";
  let sawDone = false;
  const activeContext = currentActiveContext();
  state.editorDirty = false;
  const controller = new AbortController();

  const stopHandler = async (e) => {
    e?.preventDefault?.();
    $("stopBtn").disabled = true;
    $("stopBtn").innerHTML = `<svg viewBox="0 0 24 24" fill="currentColor"><rect x="4" y="4" width="16" height="16" rx="2"/></svg> Stopping...`;
    controller.abort();
    ctx.showStreamNotice("⛔ Stopping generation...");
    try {
      await fetch("/api/cancel", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({}) });
    } catch (_) {}
  };
  $("stopBtn").addEventListener("click", stopHandler, { once: true });

  const ctx = {
    ensureStreamTarget: (placeholder = "Working...") => {
      if (!streamTarget || !streamTarget.isConnected) {
        streamTarget = appendStreamingAssistant();
      }
      if (!streamText && placeholder) {
        streamTarget.textContent = placeholder;
      }
      return streamTarget;
    },
    showStreamNotice: (message) => {
      ctx.ensureStreamTarget("");
      if (streamText) {
        streamText += `\n\n${message}`;
        streamTarget.textContent = streamText;
      } else {
        streamTarget.textContent = message;
      }
      $("messages").scrollTop = $("messages").scrollHeight;
    },
    appendToken: (chunk) => {
      streamText += chunk;
      streamTarget.textContent = streamText;
      const isPersian = isRTL(streamText);
      const article = streamTarget.closest("article");
      if (article) {
        article.setAttribute("dir", isPersian ? "rtl" : "ltr");
        article.classList.toggle("rtl", isPersian);
        article.classList.toggle("ltr", !isPersian);
      }
      updateGeneratedCodeFromStreaming(streamText);
      $("messages").scrollTop = $("messages").scrollHeight;
    },
    setSawDone: (val) => {
      sawDone = val;
    },
  };

  const refreshEditorAfterDone = async () => {
    if (activeContext?.path && activeContext.path !== "Generated Code") {
      try {
        await loadFile(activeContext.path);
      } catch {
        renderGeneratedArtifactFromState(true);
      }
      return;
    }
    if (!renderGeneratedArtifactFromState(true) && !setGeneratedCodeFromText(streamText, "final stream output", true)) {
      renderGeneratedCodeFromMessages(true);
    }
  };

  try {
    await streamViaHttp(prompt, activeContext, ctx, controller);

    if (sawDone) {
      await refreshEditorAfterDone();
    } else if (!controller.signal.aborted) {
      ctx.showStreamNotice("[stream completed]");
      await refreshEditorAfterDone();
    }
  } catch (err) {
    if (err.name === "AbortError") {
      ctx.showStreamNotice("⛔ Generation stopped by user.");
    } else {
      ctx.showStreamNotice(`Agent stream error: ${err.message}`);
    }
  } finally {
    $("stopBtn").removeEventListener("click", stopHandler);
    $("stopBtn").disabled = false;
    $("stopBtn").innerHTML = `<svg viewBox="0 0 24 24" fill="currentColor"><rect x="4" y="4" width="16" height="16" rx="2"/></svg> Stop`;
    $("sendBtn").style.display = "";
    $("stopBtn").style.display = "none";
    setLoading(false);
  }
}

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    activateTab(tab.dataset.tab);
    setActiveActivity(tab.dataset.tab === "settings" ? "Settings" : "Files");
  });
});

document.querySelectorAll(".activity-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    const label = btn.getAttribute("aria-label");
    setActiveActivity(label);
    if (label === "Projects") {
      showProjects();
    } else if (label === "Files") {
      showWorkbench();
      activateTab("files");
      $("fileSearch").focus();
    } else if (label === "Agent") {
      showWorkbench();
      $("promptInput").focus();
    } else if (label === "Settings") {
      showWorkbench();
      activateTab("settings");
    }
  });
});

document.querySelectorAll(".project-tab").forEach((tab) => tab.addEventListener("click", () => activateProjectTab(tab.dataset.projectTab)));
$("openCommandPalette").addEventListener("click", openCommandPalette);
$("commandSearch").addEventListener("input", () => { state.commandSelection = 0; renderCommandPalette(); });
document.querySelectorAll("[data-command-close]").forEach((element) => element.addEventListener("click", closeCommandPalette));
document.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
    event.preventDefault();
    return $("commandPalette").hidden ? openCommandPalette() : closeCommandPalette();
  }
  if ($("commandPalette").hidden) return;
  if (event.key === "Escape") {
    event.preventDefault();
    return closeCommandPalette();
  }
  const commands = filteredCommands();
  if (event.key === "ArrowDown" || event.key === "ArrowUp") {
    event.preventDefault();
    if (!commands.length) return;
    state.commandSelection = (state.commandSelection + (event.key === "ArrowDown" ? 1 : -1) + commands.length) % commands.length;
    return renderCommandPalette();
  }
  if (event.key === "Enter" && document.activeElement === $("commandSearch") && commands[state.commandSelection]) {
    event.preventDefault();
    return runCommand(commands[state.commandSelection].id);
  }
});
$("backToProjects").addEventListener("click", () => { $("projectHome").classList.remove("active"); $("projectsIndex").classList.remove("hidden"); });
$("openProjectInEditor").addEventListener("click", () => openProjectInEditor(false));
$("startProjectSession").addEventListener("click", () => openProjectInEditor(true));
$("newProjectSession").addEventListener("click", () => openProjectInEditor(true));
$("newProject").addEventListener("click", async () => { showWorkbench(); setActiveActivity("Files"); await browseWorkspace(); });
$("openRuntimeSettings").addEventListener("click", () => { showWorkbench(); setActiveActivity("Settings"); activateTab("settings"); });

$("fileSearch").addEventListener("input", renderFiles);
document.querySelectorAll(".file-view-tab").forEach((button) => button.addEventListener("click", () => activateFileView(button.dataset.fileView)));
$("syncCodeIndex").addEventListener("click", () => runCodeIndex("/api/index/sync", "Syncing codebase index..."));
$("rebuildCodeIndex").addEventListener("click", () => runCodeIndex("/api/index/rebuild", "Rebuilding codebase index..."));
$("regenerateProjectSummary").addEventListener("click", async () => {
  setLoading(true, "Regenerating project overview with the local model...", false);
  $("regenerateProjectSummary").disabled = true;
  try {
    await api("/api/index/regenerate-summary", {method: "POST", body: JSON.stringify({use_model: true})});
    await refreshCodeIndex();
  } catch (err) {
    $("indexError").textContent = friendlyErrorMessage(err.message);
    $("indexError").classList.add("visible");
  } finally {
    $("regenerateProjectSummary").disabled = false;
    setLoading(false);
  }
});
$("promptSearch").addEventListener("input", renderPrompts);
$("openWorkspace").addEventListener("click", openWorkspace);
$("browseWorkspace").addEventListener("click", browseWorkspace);
$("saveSettings").addEventListener("click", saveSettings);
$("compactMemory").addEventListener("click", compactMemory);
$("addMemoryFact").addEventListener("click", addMemoryFact);
$("addMemoryPreference").addEventListener("click", addMemoryPreference);
$("forgetProjectMemory").addEventListener("click", forgetProjectMemory);
$("resumeMemorySession").addEventListener("click", resumeMemorySession);
$("testSkills").addEventListener("click", testSkills);
$("tavilyEnabled").addEventListener("change", () => updateTavilyPanel());
$("saveTopCustomApi").addEventListener("click", refreshModels);
$("refreshModels").addEventListener("click", refreshModels);
$("modelSelect").addEventListener("change", saveSettings);
$("connMode").addEventListener("change", () => {
  updateCustomApiPanel();
  refreshModels();
});
$("savePrompt").addEventListener("click", savePrompt);
$("scanBtn").addEventListener("click", scanProject);
$("clearChat").addEventListener("click", async () => renderState(await api("/api/clear", { method: "POST", body: JSON.stringify({}) })));
$("attachFile").addEventListener("click", () => {
  if (!state.activeFile) return;
  $("promptInput").value = `Apply this change to ${state.activeFile}: `;
  $("promptInput").focus();
});
$("downloadCode").addEventListener("click", downloadCurrentCode);
$("showCodeTab").addEventListener("click", () => showEditorView("code"));
$("showGitTab").addEventListener("click", () => showEditorView("git"));
$("gitAuthMode").addEventListener("change", updateGitAuthPanel);
$("cloneGitRepo").addEventListener("click", cloneGitRepository);
$("pushGitChanges").addEventListener("click", () => previewGitPush().catch((error) => alert(error.message)));
$("approvalApprove").addEventListener("click", () => resolveApproval(true));
$("approvalReject").addEventListener("click", () => resolveApproval(false));
$("codeEditor").addEventListener("input", () => {
  state.fileContent = $("codeEditor").value;
  state.editorDirty = true;
  $("downloadCode").disabled = !state.fileContent;
  $("attachFile").disabled = !state.fileContent;
  $("codeEditorWrap").classList.toggle("empty", !state.fileContent);
  renderCodeHighlight();
  updateTokenUsage();
});
$("codeEditor").addEventListener("scroll", () => {
  syncEditorHighlightScroll();
});
$("promptInput").addEventListener("input", (e) => {
  updateTokenUsage();
  const isPersian = isRTL(e.target.value);
  e.target.setAttribute("dir", isPersian ? "rtl" : "ltr");
  e.target.classList.toggle("rtl", isPersian);
  e.target.classList.toggle("ltr", !isPersian);
});
$("chatForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const prompt = $("promptInput").value.trim();
  if (!prompt) return;
  $("promptInput").value = "";
  $("promptInput").setAttribute("dir", "auto");
  $("promptInput").classList.remove("rtl");
  $("promptInput").classList.add("ltr");
  updateTokenUsage();
  await sendPrompt(prompt);
});

function initPanelResizersAndToggles() {
  const layout = $("mainLayout") || document.querySelector(".layout");
  const leftPanel = $("workspacePanel") || document.querySelector(".workspace-panel");
  const rightPanel = $("agentPanel") || document.querySelector(".agent-panel");
  const resizerLeft = $("resizerLeft");
  const resizerRight = $("resizerRight");

  const toggleLeftBtn = $("toggleLeftSidebar");
  const toggleRightBtn = $("toggleRightSidebar");

  // Restore saved widths from localStorage
  try {
    const savedWidths = JSON.parse(localStorage.getItem("coderai_panel_widths") || "{}");
    if (savedWidths.left) {
      document.documentElement.style.setProperty("--left-panel-width", `${savedWidths.left}px`);
    }
    if (savedWidths.right) {
      document.documentElement.style.setProperty("--right-panel-width", `${savedWidths.right}px`);
    }
  } catch (_) {}

  function setLeftPanelVisible(visible) {
    if (leftPanel) leftPanel.classList.toggle("collapsed", !visible);
    if (resizerLeft) resizerLeft.classList.toggle("hidden", !visible);
    if (toggleLeftBtn) toggleLeftBtn.classList.toggle("active", visible);
    savePanelVisibility();
  }

  function setRightPanelVisible(visible) {
    if (rightPanel) rightPanel.classList.toggle("collapsed", !visible);
    if (resizerRight) resizerRight.classList.toggle("hidden", !visible);
    if (toggleRightBtn) toggleRightBtn.classList.toggle("active", visible);
    savePanelVisibility();
  }

  function savePanelVisibility() {
    try {
      const vis = {
        left: !leftPanel?.classList.contains("collapsed"),
        right: !rightPanel?.classList.contains("collapsed"),
      };
      localStorage.setItem("coderai_panel_visibility", JSON.stringify(vis));
    } catch (_) {}
  }

  // Restore saved visibility
  try {
    const savedVis = JSON.parse(localStorage.getItem("coderai_panel_visibility") || "{}");
    if (savedVis.left === false) {
      setLeftPanelVisible(false);
    }
    if (savedVis.right === false) {
      setRightPanelVisible(false);
    }
  } catch (_) {}

  // The TWO dedicated toggle button listeners
  if (toggleLeftBtn) {
    toggleLeftBtn.addEventListener("click", () => {
      const isCollapsed = leftPanel?.classList.contains("collapsed");
      setLeftPanelVisible(isCollapsed);
    });
  }

  if (toggleRightBtn) {
    toggleRightBtn.addEventListener("click", () => {
      const isCollapsed = rightPanel?.classList.contains("collapsed");
      setRightPanelVisible(isCollapsed);
    });
  }

  // Pointer-based draggable resizers
  function setupDraggableSplitter(resizer, onDrag) {
    if (!resizer) return;

    const onPointerMove = (e) => {
      onDrag(e);
    };

    const onPointerUp = () => {
      resizer.classList.remove("is-dragging");
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
    };

    resizer.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      resizer.classList.add("is-dragging");
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
      window.addEventListener("pointermove", onPointerMove);
      window.addEventListener("pointerup", onPointerUp);
    });
  }

  if (resizerLeft && layout) {
    setupDraggableSplitter(resizerLeft, (e) => {
      const layoutRect = layout.getBoundingClientRect();
      const newWidth = Math.max(220, Math.min(650, e.clientX - layoutRect.left));
      document.documentElement.style.setProperty("--left-panel-width", `${newWidth}px`);
      try {
        const widths = JSON.parse(localStorage.getItem("coderai_panel_widths") || "{}");
        widths.left = newWidth;
        localStorage.setItem("coderai_panel_widths", JSON.stringify(widths));
      } catch (_) {}
    });
  }

  if (resizerRight && layout) {
    setupDraggableSplitter(resizerRight, (e) => {
      const layoutRect = layout.getBoundingClientRect();
      const newWidth = Math.max(280, Math.min(850, layoutRect.right - e.clientX));
      document.documentElement.style.setProperty("--right-panel-width", `${newWidth}px`);
      try {
        const widths = JSON.parse(localStorage.getItem("coderai_panel_widths") || "{}");
        widths.right = newWidth;
        localStorage.setItem("coderai_panel_widths", JSON.stringify(widths));
      } catch (_) {}
    });
  }

  // Keyboard shortcuts (Ctrl+B for left panel, Ctrl+J for chat panel)
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "b" && !e.shiftKey && !e.altKey) {
      if (document.activeElement?.tagName === "INPUT" || document.activeElement?.tagName === "TEXTAREA") {
        return;
      }
      e.preventDefault();
      const isCollapsed = leftPanel?.classList.contains("collapsed");
      setLeftPanelVisible(isCollapsed);
    } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "j" && !e.shiftKey && !e.altKey) {
      if (document.activeElement?.tagName === "INPUT" || document.activeElement?.tagName === "TEXTAREA") {
        return;
      }
      e.preventDefault();
      const isCollapsed = rightPanel?.classList.contains("collapsed");
      setRightPanelVisible(isCollapsed);
    }
  });
}

function setupSkillSlashAutocomplete() {
  const input = $("promptInput");
  const popover = $("skillAutocomplete");
  if (!input || !popover) return;

  let selectedIndex = 0;
  let activeMatches = [];
  let slashRange = null; // { start, end, query }

  function getAvailableSkills() {
    return (state.data?.skills || []).filter((s) => !s.disabled);
  }

  function getSlashContext() {
    const text = input.value;
    const caret = input.selectionStart;
    if (caret === undefined || caret === null) return null;

    const beforeCaret = text.slice(0, caret);
    const match = beforeCaret.match(/(?:^|\s)\/([a-zA-Z0-9_\-]*)$/);
    if (!match) return null;

    const slashIndex = beforeCaret.lastIndexOf("/");
    return {
      start: slashIndex,
      end: caret,
      query: match[1].toLowerCase(),
    };
  }

  function renderAutocompleteList() {
    const ctx = getSlashContext();
    if (!ctx) {
      closeAutocomplete();
      return;
    }

    slashRange = ctx;
    const allSkills = getAvailableSkills();
    activeMatches = allSkills.filter((s) => {
      if (!ctx.query) return true;
      return (
        s.name.toLowerCase().includes(ctx.query) ||
        (s.description && s.description.toLowerCase().includes(ctx.query)) ||
        (s.category && s.category.toLowerCase().includes(ctx.query))
      );
    });

    if (!activeMatches.length) {
      popover.innerHTML = `
        <div class="skill-autocomplete-header">Skills (0)</div>
        <div class="skill-autocomplete-empty">No skills matching "/${escapeHtml(ctx.query)}"</div>
      `;
      popover.hidden = false;
      return;
    }

    if (selectedIndex >= activeMatches.length) {
      selectedIndex = 0;
    } else if (selectedIndex < 0) {
      selectedIndex = activeMatches.length - 1;
    }

    popover.innerHTML = `
      <div class="skill-autocomplete-header">
        <span>Skills (${activeMatches.length})</span>
        <span>↑↓ Navigate · Enter / Click to select</span>
      </div>
      ${activeMatches.map((skill, index) => `
        <div class="skill-autocomplete-item ${index === selectedIndex ? "active" : ""}" data-index="${index}" data-skill="${escapeHtml(skill.name)}">
          <span class="skill-autocomplete-name">/${escapeHtml(skill.name)}</span>
          <span class="skill-autocomplete-desc">${escapeHtml(skill.description || "")}</span>
          <span class="skill-autocomplete-badge">${escapeHtml(skill.category || "skill")}</span>
        </div>
      `).join("")}
    `;
    popover.hidden = false;

    const activeEl = popover.querySelector(`.skill-autocomplete-item[data-index="${selectedIndex}"]`);
    if (activeEl) {
      activeEl.scrollIntoView({ block: "nearest" });
    }

    popover.querySelectorAll(".skill-autocomplete-item").forEach((item) => {
      const idx = parseInt(item.dataset.index, 10);
      item.addEventListener("mouseenter", () => {
        selectedIndex = idx;
        popover.querySelectorAll(".skill-autocomplete-item").forEach((el, i) => {
          el.classList.toggle("active", i === selectedIndex);
        });
      });
      item.addEventListener("mousedown", (e) => {
        e.preventDefault();
        selectSkill(activeMatches[idx]);
      });
    });
  }

  function selectSkill(skill) {
    if (!skill || !slashRange) return;
    const text = input.value;
    const before = text.slice(0, slashRange.start);
    const after = text.slice(slashRange.end);
    const insertion = `/${skill.name} `;
    input.value = before + insertion + after;
    const newCaret = before.length + insertion.length;
    input.focus();
    input.setSelectionRange(newCaret, newCaret);
    closeAutocomplete();
    updateTokenUsage();
  }

  function closeAutocomplete() {
    popover.hidden = true;
    activeMatches = [];
    slashRange = null;
    selectedIndex = 0;
  }

  input.addEventListener("input", () => {
    renderAutocompleteList();
  });

  input.addEventListener("click", () => {
    renderAutocompleteList();
  });

  input.addEventListener("blur", () => {
    setTimeout(() => {
      if (!popover.matches(":hover")) {
        closeAutocomplete();
      }
    }, 150);
  });

  input.addEventListener("keydown", (e) => {
    if (popover.hidden || !activeMatches.length) {
      return;
    }

    if (e.key === "ArrowDown") {
      e.preventDefault();
      selectedIndex = (selectedIndex + 1) % activeMatches.length;
      renderAutocompleteList();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      selectedIndex = (selectedIndex - 1 + activeMatches.length) % activeMatches.length;
      renderAutocompleteList();
    } else if (e.key === "Enter" || e.key === "Tab") {
      if (activeMatches[selectedIndex]) {
        e.preventDefault();
        selectSkill(activeMatches[selectedIndex]);
      }
    } else if (e.key === "Escape") {
      e.preventDefault();
      closeAutocomplete();
    }
  });
}

// ── Interactive Schematic Architecture & Function Dependency Graph ──

let schematicGraphState = {
  nodes: [],
  edges: [],
  nodeMap: new Map(),
  transform: { x: 0, y: 0, scale: 1 },
  isDragging: false,
  dragTarget: null,
  dragStart: { x: 0, y: 0 },
  hoveredNode: null,
  isFullscreen: false,
  lastWorkspace: null,
};

async function refreshSchematicGraph(force = false) {
  const currentWs = state.data?.workspace?.path;
  if (!currentWs) return;
  if (!force && schematicGraphState.lastWorkspace === currentWs && schematicGraphState.nodes.length > 0) {
    return;
  }
  schematicGraphState.lastWorkspace = currentWs;

  try {
    const data = await api("/api/index/graph");
    renderSchematicGraphData(data);
  } catch (err) {
    const emptyEl = $("schematicGraphEmpty");
    if (emptyEl) {
      emptyEl.style.display = "flex";
      emptyEl.textContent = "Could not load architecture graph";
    }
  }
}

function renderSchematicGraphData(data) {
  const rawNodes = data?.nodes || [];
  const rawEdges = data?.edges || [];
  const emptyEl = $("schematicGraphEmpty");

  if (!rawNodes.length) {
    if (emptyEl) {
      emptyEl.style.display = "flex";
      emptyEl.textContent = "No graph relationships found";
    }
    schematicGraphState.nodes = [];
    schematicGraphState.edges = [];
    drawSchematicCanvas();
    return;
  }

  if (emptyEl) emptyEl.style.display = "none";

  const fileNodes = rawNodes.filter((n) => n.type === "file");
  const symbolNodes = rawNodes.filter((n) => n.type !== "file");

  const canvas = $("schematicCanvas");
  const width = canvas ? (canvas.clientWidth || 300) : 300;
  const height = canvas ? (canvas.clientHeight || 200) : 200;

  const nodeMap = new Map();
  const nodes = [];

  const fileCount = Math.max(1, fileNodes.length);
  const rx = Math.max(100, Math.min(width * 0.35, 240));
  const ry = Math.max(60, Math.min(height * 0.3, 140));
  const cx = width / 2;
  const cy = height / 2;

  fileNodes.forEach((fn, idx) => {
    const angle = (idx / fileCount) * 2 * Math.PI - Math.PI / 2;
    const fx = cx + rx * Math.cos(angle);
    const fy = cy + ry * Math.sin(angle);

    const nodeObj = {
      id: fn.id,
      label: fn.label || fn.id,
      full_path: fn.full_path || fn.id,
      type: "file",
      is_entry: !!fn.is_entry,
      symbols_count: fn.symbols_count || 0,
      docstring: fn.docstring || "",
      x: fx,
      y: fy,
      width: Math.max(70, Math.min(130, (fn.label || fn.id).length * 7 + 26)),
      height: 26,
    };
    nodes.push(nodeObj);
    nodeMap.set(fn.id, nodeObj);

    const fileSymbols = symbolNodes.filter((s) => s.file_path === fn.id);
    const symCount = fileSymbols.length;
    fileSymbols.forEach((sn, sIdx) => {
      const sAngle = angle + ((sIdx + 1) / (symCount + 1) - 0.5) * 1.5;
      const sDist = 45 + (sIdx % 2) * 15;
      const sx = fx + sDist * Math.cos(sAngle);
      const sy = fy + sDist * Math.sin(sAngle);

      const symObj = {
        id: sn.id,
        label: sn.label,
        file_path: sn.file_path,
        type: sn.type || "function",
        x: sx,
        y: sy,
        width: Math.max(50, Math.min(100, (sn.label || "").length * 6 + 18)),
        height: 18,
      };
      nodes.push(symObj);
      nodeMap.set(sn.id, symObj);
    });
  });

  const edges = [];
  rawEdges.forEach((e) => {
    const src = nodeMap.get(e.source);
    const tgt = nodeMap.get(e.target);
    if (src && tgt) {
      edges.push({
        source: src,
        target: tgt,
        type: e.type || "imports",
        label: e.label || "",
      });
    }
  });

  schematicGraphState.nodes = nodes;
  schematicGraphState.edges = edges;
  schematicGraphState.nodeMap = nodeMap;

  fitSchematicView();
  drawSchematicCanvas();
}

function fitSchematicView() {
  const canvas = $("schematicCanvas");
  if (!canvas || !schematicGraphState.nodes.length) return;

  const w = canvas.clientWidth || 300;
  const h = canvas.clientHeight || 200;

  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  schematicGraphState.nodes.forEach((n) => {
    minX = Math.min(minX, n.x - (n.width || 20) / 2);
    maxX = Math.max(maxX, n.x + (n.width || 20) / 2);
    minY = Math.min(minY, n.y - (n.height || 20) / 2);
    maxY = Math.max(maxY, n.y + (n.height || 20) / 2);
  });

  const graphW = Math.max(50, maxX - minX);
  const graphH = Math.max(50, maxY - minY);
  const padding = 40;

  const scaleX = (w - padding * 2) / graphW;
  const scaleY = (h - padding * 2) / graphH;
  const scale = Math.max(0.4, Math.min(1.4, Math.min(scaleX, scaleY)));

  const midX = (minX + maxX) / 2;
  const midY = (minY + maxY) / 2;

  schematicGraphState.transform = {
    scale,
    x: w / 2 - midX * scale,
    y: h / 2 - midY * scale,
  };
}

function drawSchematicCanvas() {
  const canvas = $("schematicCanvas");
  if (!canvas) return;

  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  const w = Math.max(10, rect.width);
  const h = Math.max(10, rect.height);

  if (canvas.width !== Math.floor(w * dpr) || canvas.height !== Math.floor(h * dpr)) {
    canvas.width = Math.floor(w * dpr);
    canvas.height = Math.floor(h * dpr);
  }

  const ctx = canvas.getContext("2d");
  ctx.save();
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, w, h);

  const bgGrad = ctx.createRadialGradient(w / 2, h / 2, 20, w / 2, h / 2, Math.max(w, h));
  bgGrad.addColorStop(0, "#14171d");
  bgGrad.addColorStop(1, "#0d0f12");
  ctx.fillStyle = bgGrad;
  ctx.fillRect(0, 0, w, h);

  const { x, y, scale } = schematicGraphState.transform;
  ctx.save();
  ctx.translate(x, y);
  ctx.scale(scale, scale);

  const hovered = schematicGraphState.hoveredNode;

  // 1. Draw Edges
  schematicGraphState.edges.forEach((edge) => {
    const src = edge.source;
    const tgt = edge.target;
    if (!src || !tgt) return;

    const isConnectedToHover = hovered && (hovered === src || hovered === tgt);
    ctx.beginPath();
    ctx.moveTo(src.x, src.y);

    if (edge.type === "defines") {
      ctx.strokeStyle = isConnectedToHover ? "rgba(16, 185, 129, 0.85)" : "rgba(255, 255, 255, 0.12)";
      ctx.lineWidth = isConnectedToHover ? 2 : 1;
      ctx.setLineDash([2, 3]);
      ctx.lineTo(tgt.x, tgt.y);
      ctx.stroke();
      ctx.setLineDash([]);
    } else {
      const dx = tgt.x - src.x;
      const dy = tgt.y - src.y;
      const cx = (src.x + tgt.x) / 2 - dy * 0.15;
      const cy = (src.y + tgt.y) / 2 + dx * 0.15;

      ctx.strokeStyle = isConnectedToHover ? "rgba(59, 130, 246, 0.95)" : "rgba(59, 130, 246, 0.4)";
      ctx.lineWidth = isConnectedToHover ? 2.5 : 1.4;
      ctx.quadraticCurveTo(cx, cy, tgt.x, tgt.y);
      ctx.stroke();

      const angle = Math.atan2(tgt.y - cy, tgt.x - cx);
      const arrowLen = 6;
      ctx.beginPath();
      ctx.moveTo(tgt.x, tgt.y);
      ctx.lineTo(tgt.x - arrowLen * Math.cos(angle - Math.PI / 6), tgt.y - arrowLen * Math.sin(angle - Math.PI / 6));
      ctx.lineTo(tgt.x - arrowLen * Math.cos(angle + Math.PI / 6), tgt.y - arrowLen * Math.sin(angle + Math.PI / 6));
      ctx.closePath();
      ctx.fillStyle = ctx.strokeStyle;
      ctx.fill();
    }
  });

  // 2. Draw Nodes
  schematicGraphState.nodes.forEach((node) => {
    const isHovered = hovered === node;
    const isFile = node.type === "file";
    const isFunc = node.type === "function";
    const isClass = node.type === "class";

    const nw = node.width || (isFile ? 80 : 60);
    const nh = node.height || (isFile ? 26 : 18);
    const nx = node.x - nw / 2;
    const ny = node.y - nh / 2;
    const r = isFile ? 6 : 9;

    ctx.beginPath();
    ctx.roundRect(nx, ny, nw, nh, r);

    if (isFile) {
      if (node.is_entry) {
        ctx.fillStyle = isHovered ? "#3b1720" : "#241419";
        ctx.strokeStyle = isHovered ? "#f43f5e" : "#e11d48";
      } else {
        ctx.fillStyle = isHovered ? "#172554" : "#0f172a";
        ctx.strokeStyle = isHovered ? "#60a5fa" : "#3b82f6";
      }
      ctx.lineWidth = isHovered ? 2.2 : 1.2;
    } else if (isFunc) {
      ctx.fillStyle = isHovered ? "#064e3b" : "#022c22";
      ctx.strokeStyle = isHovered ? "#34d399" : "#10b981";
      ctx.lineWidth = isHovered ? 2 : 1;
    } else if (isClass) {
      ctx.fillStyle = isHovered ? "#78350f" : "#451a03";
      ctx.strokeStyle = isHovered ? "#fbbf24" : "#f59e0b";
      ctx.lineWidth = isHovered ? 2 : 1;
    }

    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = isHovered ? "#ffffff" : "#e2e8f0";
    ctx.font = isFile ? "bold 10.5px Inter, sans-serif" : "9px JetBrains Mono, monospace";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";

    let label = node.label || node.id;
    if (label.length > 14) label = label.slice(0, 12) + "…";
    ctx.fillText(label, node.x, node.y + (isFile ? 0 : 0.5));
  });

  ctx.restore();
  ctx.restore();
}

function initSchematicArchitectureGraph() {
  const container = $("schematicCanvasContainer");
  const box = $("schematicGraphBox");
  const canvas = $("schematicCanvas");
  const tooltip = $("schematicTooltip");
  const toggleBtn = $("toggleSchematicFullscreen");
  const refreshBtn = $("refreshSchematicGraph");

  if (!container || !canvas || !box) return;

  const ro = new ResizeObserver(() => {
    drawSchematicCanvas();
  });
  ro.observe(container);

  function toggleFullscreen() {
    schematicGraphState.isFullscreen = !schematicGraphState.isFullscreen;
    box.classList.toggle("fullscreen", schematicGraphState.isFullscreen);

    let backdrop = document.querySelector(".schematic-backdrop");
    if (schematicGraphState.isFullscreen) {
      if (!backdrop) {
        backdrop = document.createElement("div");
        backdrop.className = "schematic-backdrop";
        backdrop.addEventListener("click", toggleFullscreen);
        document.body.appendChild(backdrop);
      }
      $("schematicExpandIcon").style.display = "none";
      $("schematicCompressIcon").style.display = "block";
    } else {
      if (backdrop) backdrop.remove();
      $("schematicExpandIcon").style.display = "block";
      $("schematicCompressIcon").style.display = "none";
    }

    setTimeout(() => {
      fitSchematicView();
      drawSchematicCanvas();
    }, 50);
  }

  // Double click anywhere on the graph box toggles fullscreen
  box.addEventListener("dblclick", (e) => {
    if (e.target.closest("button")) return;
    toggleFullscreen();
  });

  if (toggleBtn) {
    toggleBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      toggleFullscreen();
    });
  }

  if (refreshBtn) {
    refreshBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      refreshSchematicGraph(true);
    });
  }

  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && schematicGraphState.isFullscreen) {
      toggleFullscreen();
    }
  });

  function getGraphCoords(e) {
    const rect = canvas.getBoundingClientRect();
    const clientX = e.clientX - rect.left;
    const clientY = e.clientY - rect.top;
    const { x, y, scale } = schematicGraphState.transform;
    return {
      gx: (clientX - x) / scale,
      gy: (clientY - y) / scale,
      screenX: e.clientX,
      screenY: e.clientY,
      localX: clientX,
      localY: clientY,
    };
  }

  function findNodeAt(gx, gy) {
    for (let i = schematicGraphState.nodes.length - 1; i >= 0; i--) {
      const n = schematicGraphState.nodes[i];
      const nw = (n.width || 60) / 2;
      const nh = (n.height || 20) / 2;
      if (gx >= n.x - nw && gx <= n.x + nw && gy >= n.y - nh && gy <= n.y + nh) {
        return n;
      }
    }
    return null;
  }

  container.addEventListener("mousedown", (e) => {
    if (e.button !== 0) return;
    const { gx, gy, localX, localY } = getGraphCoords(e);
    const hitNode = findNodeAt(gx, gy);

    if (hitNode) {
      schematicGraphState.dragTarget = hitNode;
      schematicGraphState.dragStart = { x: gx - hitNode.x, y: gy - hitNode.y };
    } else {
      schematicGraphState.isDragging = true;
      schematicGraphState.dragStart = { x: localX - schematicGraphState.transform.x, y: localY - schematicGraphState.transform.y };
    }
  });

  window.addEventListener("mousemove", (e) => {
    const { gx, gy, localX, localY } = getGraphCoords(e);

    if (schematicGraphState.dragTarget) {
      schematicGraphState.dragTarget.x = gx - schematicGraphState.dragStart.x;
      schematicGraphState.dragTarget.y = gy - schematicGraphState.dragStart.y;
      drawSchematicCanvas();
      return;
    }

    if (schematicGraphState.isDragging) {
      schematicGraphState.transform.x = localX - schematicGraphState.dragStart.x;
      schematicGraphState.transform.y = localY - schematicGraphState.dragStart.y;
      drawSchematicCanvas();
      return;
    }

    const hitNode = findNodeAt(gx, gy);
    if (hitNode !== schematicGraphState.hoveredNode) {
      schematicGraphState.hoveredNode = hitNode;
      drawSchematicCanvas();

      if (hitNode && tooltip) {
        let text = `<strong>${escapeHtml(hitNode.label)}</strong> (${hitNode.type})`;
        if (hitNode.type === "file") {
          text += `<br><span style="color:var(--muted)">Symbols: ${hitNode.symbols_count}</span>`;
          if (hitNode.is_entry) text += `<br><span style="color:var(--danger)">★ Entry Point</span>`;
          if (hitNode.docstring) text += `<br><span style="font-size:9.5px;color:var(--text-dim)">${escapeHtml(hitNode.docstring.slice(0, 100))}</span>`;
        } else {
          text += `<br><span style="color:var(--muted)">In: ${escapeHtml(hitNode.file_path || "")}</span>`;
        }
        tooltip.innerHTML = text;
        tooltip.style.left = `${Math.min(localX + 12, container.clientWidth - 180)}px`;
        tooltip.style.top = `${Math.min(localY + 12, container.clientHeight - 80)}px`;
        tooltip.style.display = "block";
      } else if (tooltip) {
        tooltip.style.display = "none";
      }
    }
  });

  window.addEventListener("mouseup", () => {
    schematicGraphState.isDragging = false;
    schematicGraphState.dragTarget = null;
  });

  container.addEventListener("wheel", (e) => {
    e.preventDefault();
    const { localX, localY } = getGraphCoords(e);
    const zoomFactor = e.deltaY < 0 ? 1.15 : 0.87;
    const newScale = Math.max(0.2, Math.min(3.5, schematicGraphState.transform.scale * zoomFactor));

    schematicGraphState.transform.x = localX - (localX - schematicGraphState.transform.x) * (newScale / schematicGraphState.transform.scale);
    schematicGraphState.transform.y = localY - (localY - schematicGraphState.transform.y) * (newScale / schematicGraphState.transform.scale);
    schematicGraphState.transform.scale = newScale;

    drawSchematicCanvas();
  }, { passive: false });

  container.addEventListener("click", (e) => {
    const { gx, gy } = getGraphCoords(e);
    const hitNode = findNodeAt(gx, gy);
    if (hitNode && (hitNode.type === "file" || hitNode.file_path)) {
      const targetPath = hitNode.type === "file" ? hitNode.full_path : hitNode.file_path;
      if (targetPath) loadFile(targetPath);
    }
  });
}

initPanelResizersAndToggles();
setupSkillSlashAutocomplete();
initSchematicArchitectureGraph();
installEditorMetricStyles();
updateGitAuthPanel();
refresh().catch((err) => {
  $("messages").innerHTML = `<article class="message assistant"><span class="role">error</span>${escapeHtml(err.message)}</article>`;
}).then(() => {
  if (!state.initialProjectsShown) {
    state.initialProjectsShown = true;
    setActiveActivity("Projects");
    showProjects().catch(() => showWorkbench());
  }
});
