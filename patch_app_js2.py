import pathlib
path = pathlib.Path('E:/llm_projects/agantic_ai/ollama_workspace_v4/web_ui/app.js')
text = path.read_text('utf-8')
text = text.replace('if (promptInput) promptInput.focus();', 'const pi = document.getElementById("promptInput"); if (pi) pi.focus();')
path.write_text(text, 'utf-8')
