import pathlib
path = pathlib.Path('E:/llm_projects/agantic_ai/ollama_workspace_v4/web_ui/app.js')
text = path.read_text('utf-8')

# Fix Monaco initialization
old_init = '''            value: state.fileContent || "",
            language: 'plaintext',
            theme: 'vs-dark','''

new_init = '''            value: state.fileContent || "",
            language: (() => {
                let ext = (state.activeFile || "").split('.').pop().toLowerCase();
                const langMap = { "js": "javascript", "ts": "typescript", "py": "python", "html": "html", "css": "css", "json": "json", "md": "markdown", "sh": "shell", "bash": "shell", "sql": "sql", "yaml": "yaml", "yml": "yaml", "xml": "xml", "go": "go", "java": "java", "cpp": "cpp", "c": "c", "cs": "csharp", "php": "php", "rb": "ruby" };
                return langMap[ext] || "plaintext";
            })(),
            theme: 'vs-dark','''

text = text.replace(old_init, new_init)
path.write_text(text, 'utf-8')
