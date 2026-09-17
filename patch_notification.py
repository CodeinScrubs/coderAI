import pathlib
path = pathlib.Path('E:/llm_projects/agantic_ai/ollama_workspace_v4/web_app.py')
text = path.read_text('utf-8')

old = 'write_event({"type": "status", "message": "Preparing context..."})'
new = '''write_event({"type": "status", "message": "Preparing context..."})
    
    # Check if memory compaction will be triggered
    if STATE.get("memory_enabled") and len(STATE.get("messages", [])) > max(MAX_KEPT_HISTORY_MESSAGES + 2, 18):
        write_event({"type": "status", "message": "Auto-compacting memory... (This may take a minute to summarize history)"})
'''

if 'Auto-compacting memory...' not in text:
    text = text.replace(old, new)
    path.write_text(text, 'utf-8')
    print("Added UI notification for auto-compaction")
else:
    print("Already added UI notification")
