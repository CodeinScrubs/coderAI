import pathlib
path = pathlib.Path('E:/llm_projects/agantic_ai/ollama_workspace_v4/fastapi_app.py')
text = path.read_text('utf-8')
text = text.replace('web_app._client_state(sid)', 'web_app._client_state()')
path.write_text(text, 'utf-8')
