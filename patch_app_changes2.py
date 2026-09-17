import pathlib

path = pathlib.Path('E:/llm_projects/agantic_ai/ollama_workspace_v4/web_ui/app.js')
text = path.read_text('utf-8')

old = '''        const response = await api("/api/git/status");
        if (response.error) {
            list.innerHTML = <div style='padding: 1rem; color: var(--danger-color);'></div>;
            return;
        }
        const files = response.status?.files || [];'''

new = '''        const response = await api("/api/git");
        if (response.error && !response.is_repo) {
            list.innerHTML = <div style='padding: 1rem; color: var(--danger-color);'>Git not connected</div>;
            return;
        }
        const files = response.files || [];'''

text = text.replace(old, new)
path.write_text(text, 'utf-8')
print("Patched app.js with /api/git")
