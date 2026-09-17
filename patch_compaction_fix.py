import pathlib

path = pathlib.Path('E:/llm_projects/agantic_ai/ollama_workspace_v4/web_app.py')
text = path.read_text('utf-8')

old_compact_try = '''    try:
        # We temporarily disable tools for the summarizer
        old_tools = STATE.get("active_tools", [])
        # We don't need to change state tools if _call_model respects _active_tool_schemas, but we can't easily override it without a hack.
        # So we'll just run _call_model and ignore tool calls.
        summary_history = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        response = _call_model(summary_history)'''

new_compact_try = '''    try:
        old_tools = STATE.get("active_tools", [])
        STATE["active_tools"] = []
        old_budget = STATE.get("response_token_budget", DEFAULT_RESPONSE_TOKEN_BUDGET)
        STATE["response_token_budget"] = 1500  # limit summary length
        
        summary_history = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        # We need a way to notify the user if it's called inside a streaming context
        # But since we don't have write_event here, we just let it take its time.
        response = _call_model(summary_history)
        
        STATE["active_tools"] = old_tools
        STATE["response_token_budget"] = old_budget
'''

if 'STATE["active_tools"] = []' not in text:
    text = text.replace(old_compact_try, new_compact_try)
    path.write_text(text, 'utf-8')
    print("Fixed compaction bug")
else:
    print("Already fixed")
