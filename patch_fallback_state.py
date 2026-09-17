import pathlib

path = pathlib.Path('E:/llm_projects/agantic_ai/ollama_workspace_v4/web_app.py')
text = path.read_text('utf-8')

old = '''    "custom_api_model": "gpt-4o-mini",'''
new = '''    "custom_api_model": "gpt-4o-mini",
    "fallback_model": "",'''
text = text.replace(old, new)

old_sync = '''            "custom_api_url", "custom_api_key", "custom_api_model", "memory_enabled",'''
new_sync = '''            "custom_api_url", "custom_api_key", "custom_api_model", "fallback_model", "memory_enabled",'''
text = text.replace(old_sync, new_sync)

old_payload = '''            "custom_api_model": st["custom_api_model"],'''
new_payload = '''            "custom_api_model": st["custom_api_model"],
            "fallback_model": st.get("fallback_model", ""),'''
text = text.replace(old_payload, new_payload)

old_set = '''                if "custom_api_model" in data and str(data["custom_api_model"] or "").strip():
                    STATE["custom_api_model"] = str(data["custom_api_model"]).strip()'''
new_set = '''                if "custom_api_model" in data and str(data["custom_api_model"] or "").strip():
                    STATE["custom_api_model"] = str(data["custom_api_model"]).strip()
                if "fallback_model" in data:
                    STATE["fallback_model"] = str(data["fallback_model"]).strip()'''
text = text.replace(old_set, new_set)

path.write_text(text, 'utf-8')
print("Patched fallback state")
