import pathlib

path = pathlib.Path('E:/llm_projects/agantic_ai/ollama_workspace_v4/agent_runtime.py')
text = path.read_text('utf-8')

old = '''            api_key = settings.custom_api_key or "not-needed"
            base_url = settings.custom_api_url.rstrip("/") if settings.custom_api_url else "https://api.openai.com/v1"

            return ChatOpenAI('''

new = '''            api_key = settings.custom_api_key or "not-needed"
            base_url = settings.custom_api_url.rstrip("/") if settings.custom_api_url else "https://api.openai.com/v1"
            if base_url.endswith("/chat/completions"):
                base_url = base_url[:-17]

            return ChatOpenAI('''

text = text.replace(old, new)
path.write_text(text, 'utf-8')

path2 = pathlib.Path('E:/llm_projects/agantic_ai/ollama_workspace_v4/web_app.py')
text2 = path2.read_text('utf-8')

old2 = '''      tool_call_deltas: dict[int, dict] = {}
      finish_reason = ""
      for event in _post_json_stream(
          f"{STATE['custom_api_url'].rstrip('/')}/chat/completions",'''

new2 = '''      tool_call_deltas: dict[int, dict] = {}
      finish_reason = ""
      
      base_url = STATE['custom_api_url'].rstrip('/')
      if base_url.endswith("/chat/completions"):
          base_url = base_url[:-17]
          
      for event in _post_json_stream(
          f"{base_url}/chat/completions",'''

text2 = text2.replace(old2, new2)
path2.write_text(text2, 'utf-8')

print("Fixed double /chat/completions")
