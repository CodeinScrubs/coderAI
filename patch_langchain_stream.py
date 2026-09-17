import pathlib

path = pathlib.Path('E:/llm_projects/agantic_ai/ollama_workspace_v4/web_app.py')
text = path.read_text('utf-8')

old = '''def _use_langchain_streaming_runtime() -> bool:
    return os.getenv("AGENT_USE_LANGCHAIN_STREAMING", "false").lower() in {"1", "true", "yes"}'''

new = '''def _use_langchain_streaming_runtime() -> bool:
    if "custom" in str(STATE.get("conn_mode", "")).lower():
        return True
    return os.getenv("AGENT_USE_LANGCHAIN_STREAMING", "false").lower() in {"1", "true", "yes"}'''

if "STATE.get(\"conn_mode\"" not in text.split("def _use_langchain_streaming_runtime")[1][:200]:
    text = text.replace(old, new)
    path.write_text(text, 'utf-8')
    print("Enabled langchain streaming for Custom API")
else:
    print("Already enabled")
