import pathlib

path = pathlib.Path('E:/llm_projects/agantic_ai/ollama_workspace_v4/web_ui/app.js')
text = path.read_text('utf-8')

old = '''function activateTab(tabId) {
  document.querySelectorAll(".workspace-tabs .tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === tabId));
  document.querySelectorAll(".tab-page").forEach((p) => {
    p.classList.toggle("active", p.id === ${tabId}Tab);
    if (p.id === ${tabId}Tab) {
      p.style.display = "flex";
    } else {
      p.style.display = "none";
    }
  });
}'''

new = '''function activateTab(tabId) {
  document.querySelectorAll(".workspace-tabs .tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === tabId));
  document.querySelectorAll(".tab-page").forEach((p) => {
    p.classList.toggle("active", p.id === ${tabId}Tab);
    if (p.id === ${tabId}Tab) {
      p.style.display = "flex";
    } else {
      p.style.display = "none";
    }
  });
  if (tabId === "changes") {
    refreshSessionChanges();
  }
}

async function refreshSessionChanges() {
    const list = sessionChangesList;
    if (!list) return;
    list.innerHTML = "<div style='padding: 1rem; color: var(--text-muted);'>Loading changes...</div>";
    try {
        const response = await api("/api/git/status");
        if (response.error) {
            list.innerHTML = <div style='padding: 1rem; color: var(--danger-color);'></div>;
            return;
        }
        const files = response.status?.files || [];
        if (files.length === 0) {
            list.innerHTML = "<div style='padding: 1rem; color: var(--text-muted);'>No uncommitted changes in this session.</div>";
            return;
        }
        list.innerHTML = files.map(f => 
            <div class="file-item" style="display: flex; justify-content: space-between; align-items: center; padding: 0.5rem;">
                <span class="file-name" style="flex: 1; word-break: break-all;"></span>
                <span class="file-status" style="color: var(--accent-color); font-size: 0.8rem; margin-left: 0.5rem; text-transform: uppercase;"></span>
            </div>
        ).join("");
    } catch (e) {
        list.innerHTML = <div style='padding: 1rem; color: var(--danger-color);'>Failed to load changes: </div>;
    }
}
'''
if "refreshSessionChanges" not in text:
    text = text.replace(old, new)
    path.write_text(text, 'utf-8')
    print("Added logic to app.js")
else:
    print("Already added logic")
