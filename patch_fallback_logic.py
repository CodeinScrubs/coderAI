import pathlib

path = pathlib.Path('E:/llm_projects/agantic_ai/ollama_workspace_v4/web_app.py')
text = path.read_text('utf-8')

old = '''            write_event({
                "type": "status",
                "message": f"Waiting for {_active_model_display()} ({iteration + 1}/{MAX_ITERATIONS}, timeout {REQUEST_TIMEOUT}s)...",
            })
            result = _call_model_stream(history, write_event)'''

new = '''            write_event({
                "type": "status",
                "message": f"Waiting for {_active_model_display()} ({iteration + 1}/{MAX_ITERATIONS}, timeout {REQUEST_TIMEOUT}s)...",
            })
            
            try:
                result = _call_model_stream(history, write_event)
            except Exception as e:
                fallback = str(STATE.get("fallback_model", "")).strip()
                if fallback and fallback != STATE.get("custom_api_model") and fallback != STATE.get("model"):
                    write_event({"type": "status", "message": f"Primary model failed ({e}). Falling back to {fallback}..."})
                    print(f"Model failed: {e}. Falling back to {fallback}")
                    
                    old_conn_mode = STATE["conn_mode"]
                    old_custom = STATE.get("custom_api_model")
                    
                    STATE["conn_mode"] = MODE_CUSTOM
                    STATE["custom_api_model"] = fallback
                    try:
                        result = _call_model_stream(history, write_event)
                    finally:
                        STATE["conn_mode"] = old_conn_mode
                        STATE["custom_api_model"] = old_custom
                else:
                    raise'''

text = text.replace(old, new)
path.write_text(text, 'utf-8')
print("Added fallback logic to web_app.py")
