import re

app_path = 'E:/llm_projects/agantic_ai/ollama_workspace_v4/web_app.py'
with open(app_path, 'r', encoding='utf-8') as f:
    code = f.read()

code = re.sub(
    r'"If you need to see the code inside this file to answer their request, use the ead_file tool\.",\s*"Do NOT guess the file contents\. Retrieve it via tool if needed\.",\s*"Use write_file or eplace_in_file to apply requested changes to this path when appropriate\.",\s*\]',
    '"Use write_file or eplace_in_file to apply requested changes to this path when appropriate.",\n                ]\n                body = _clip_for_context(content, 18_000)\n                lines += ["", f"`{(active_context.get(\'info\') or \'\').rstrip()}", body, "`"]',
    code,
    flags=re.MULTILINE
)

with open(app_path, 'w', encoding='utf-8') as f:
    f.write(code)
