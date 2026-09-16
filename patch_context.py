import re

app_path = 'E:/llm_projects/agantic_ai/ollama_workspace_v4/web_app.py'
with open(app_path, 'r', encoding='utf-8') as f:
    code = f.read()

# Replace the else block that tells the agent to use read_file
# with a block that just gives the agent the code.

old_block = '''            else:
                lines += [
                    "The user's next request is about this file unless they explicitly say otherwise.",
                    "If you need to see the code inside this file to answer their request, use the ead_file tool.",
                    "Do NOT guess the file contents. Retrieve it via tool if needed.",
                    "Use write_file or eplace_in_file to apply requested changes to this path when appropriate.",
                ]'''

new_block = '''            else:
                lines += [
                    "The user's next request is about this file unless they explicitly say otherwise.",
                    "Use write_file or eplace_in_file to apply requested changes to this path when appropriate.",
                    "The content of the active file is provided below for your immediate reference:"
                ]
                body = _clip_for_context(content, 18_000)
                lines += [
                    "",
                    f"`{active_context.get('info') or ''}".rstrip(),
                    body,
                    "`",
                ]'''

code = code.replace(old_block, new_block)

with open(app_path, 'w', encoding='utf-8') as f:
    f.write(code)
