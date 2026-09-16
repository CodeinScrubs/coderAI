import pathlib
import re
path = pathlib.Path('E:/llm_projects/agantic_ai/ollama_workspace_v4/web_app.py')
text = path.read_text('utf-8')

# Fix _call_model_stream for ollama stream
old_ollama = '''        return {
            "content": "".join(content_parts),
            "thinking": "".join(thinking_parts),
            "tool_calls": _extract_tool_calls_ollama({"tool_calls": tool_calls_raw}),
        }'''
new_ollama = '''        return {
            "content": "".join(content_parts),
            "thinking": "".join(thinking_parts),
            "tool_calls": _extract_tool_calls_ollama({"tool_calls": tool_calls_raw, "content": "".join(content_parts)}),
        }'''
text = text.replace(old_ollama, new_ollama)

path.write_text(text, 'utf-8')
