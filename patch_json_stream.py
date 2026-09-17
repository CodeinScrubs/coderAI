import pathlib

path = pathlib.Path('E:/llm_projects/agantic_ai/ollama_workspace_v4/web_app.py')
text = path.read_text('utf-8')

old = '''    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        for raw_line in resp:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            # Ignore SSE comment and keep-alive lines (e.g. ": ping", ": keepalive")
            if line.startswith(":"):
                continue
            if line.startswith("event:") or line.startswith("id:") or line.startswith("retry:"):
                continue
            if line.startswith("data:"):
                line = line[5:].strip()
            if not line:
                continue
            if line == "[DONE]":
                break
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                pass'''

new = '''    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        content_type = resp.headers.get("Content-Type", "")
        if "application/json" in content_type:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                data = json.loads(raw)
            except Exception:
                data = {"error": "Invalid JSON response", "raw": raw}
            if "error" in data:
                raise ValueError(f"API Error: {data['error']}")
            yield data
            return

        for raw_line in resp:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            if line.startswith(":"):
                continue
            if line.startswith("event:") or line.startswith("id:") or line.startswith("retry:"):
                continue
            if line.startswith("data:"):
                line = line[5:].strip()
            if not line:
                continue
            if line == "[DONE]":
                break
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                pass'''

text = text.replace(old, new)

# Also fix the Custom API stream parsing to check for errors
old_custom = '''        choices = event.get("choices", []) if isinstance(event, dict) else []
        if not choices:
            continue'''

new_custom = '''        choices = event.get("choices", []) if isinstance(event, dict) else []
        if not choices:
            if isinstance(event, dict) and "error" in event:
                raise ValueError(f"API Error: {event['error']}")
            continue'''

text = text.replace(old_custom, new_custom)

path.write_text(text, 'utf-8')
print("Patched web_app.py error handling")
