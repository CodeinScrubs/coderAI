import pathlib
path = pathlib.Path('E:/llm_projects/agantic_ai/ollama_workspace_v4/web_app.py')
text = path.read_text('utf-8')

target = '"If you need to see the code inside this file to answer their request, use the ead_file tool.",'
target2 = '"Do NOT guess the file contents. Retrieve it via tool if needed.",'

text = text.replace(target, '')
text = text.replace(target2, '')

target3 = '"Use write_file or eplace_in_file to apply requested changes to this path when appropriate.",\n                ]'

replacement = '''"Use write_file or eplace_in_file to apply requested changes to this path when appropriate.",
                ]
                body = _clip_for_context(content, 18_000)
                lines += ["", f"`{active_context.get('info') or ''}".rstrip(), body, "`"]
'''
text = text.replace(target3, replacement)

path.write_text(text, 'utf-8')
