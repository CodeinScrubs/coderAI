import pathlib

path = pathlib.Path('E:/llm_projects/agantic_ai/ollama_workspace_v4/web_ui/app.js')
text = path.read_text('utf-8')

old_render = '''      const toolHtml = tools.length ? `<div class="tool-box">${escapeHtml(tools.map((t) =>
        `${t.name}(${JSON.stringify(t.args || {})})\\n${String(t.result || "").slice(0, 1200)}`
      ).join("\\n\\n"))}</div>` : "";
      const isMsgRTL = isRTL(msg.content);
      const dirAttr = isMsgRTL ? "rtl" : "ltr";
      const roleLabel = msg.role === "user" ? "You" : "Coder AI";
      return `
        <article class="message ${msg.role} ${dirAttr}" dir="${dirAttr}">
          <div class="message-meta"><span class="role">${roleLabel}</span></div>
          <div class="message-text">${renderMessageContent(msg)}</div>
          ${toolHtml}
        </article>
      `;'''

new_render = '''      const toolHtml = tools.length ? `<div class="chat-tools">${tools.map((t) => {
        let summary = t.name;
        if (t.name === 'run_bash' && t.args.command) {
            summary = 'Run command: ' + (t.args.command.length > 50 ? t.args.command.slice(0, 50) + '...' : t.args.command);
        } else if (t.name === 'write_to_file' && t.args.file_path) {
            summary = 'Write to ' + t.args.file_path;
        } else if (t.name === 'replace_in_file' && t.args.file_path) {
            summary = 'Edit ' + t.args.file_path;
        } else if (t.name === 'search_codebase' && t.args.query) {
            summary = 'Search: ' + t.args.query;
        } else if (t.name === 'run_python') {
            summary = 'Run python snippet';
        } else if (t.name === 'read_many_files' && t.args.file_paths) {
            summary = 'Read ' + t.args.file_paths.length + ' files';
        } else if (t.name === 'get_project_overview') {
            summary = 'Analyze project overview';
        }
        const rawJsonArgs = JSON.stringify(t.args || {}, null, 2);
        const resultString = String(t.result || "").slice(0, 1500) + (String(t.result || "").length > 1500 ? "\\n... [Truncated]" : "");
        return `<details class="antigravity-tool">
          <summary>${escapeHtml(summary)} &gt;</summary>
          <pre><code>Arguments:\\n${escapeHtml(rawJsonArgs)}\\n\\nResult:\\n${escapeHtml(resultString)}</code></pre>
        </details>`;
      }).join("")}</div>` : "";
      const isMsgRTL = isRTL(msg.content);
      const dirAttr = isMsgRTL ? "rtl" : "ltr";
      const roleLabel = msg.role === "user" ? "You" : "Coder AI";
      return `
        <article class="message ${msg.role} ${dirAttr}" dir="${dirAttr}">
          <div class="message-meta"><span class="role">${roleLabel}</span></div>
          ${toolHtml}
          <div class="message-text">${renderMessageContent(msg)}</div>
        </article>
      `;'''

text = text.replace(old_render, new_render)

old_append = '''  const entry = document.createElement("details");
  entry.innerHTML = `<summary>${escapeHtml(name)}</summary><pre><code>${escapeHtml(detail)}</code></pre>`;'''

new_append = '''  const entry = document.createElement("details");
  entry.className = "antigravity-tool";
  let summary = name;
  if (detail.includes("command")) { summary = "Executing command..."; }
  else if (detail.includes("file_path")) { summary = "Modifying file..."; }
  entry.innerHTML = `<summary>${escapeHtml(summary)} &gt;</summary><pre><code>${escapeHtml(detail)}</code></pre>`;'''

text = text.replace(old_append, new_append)
path.write_text(text, 'utf-8')
print("Replaced app.js logic")
