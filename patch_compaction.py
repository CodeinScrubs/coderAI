import pathlib

path = pathlib.Path('E:/llm_projects/agantic_ai/ollama_workspace_v4/web_app.py')
text = path.read_text('utf-8')

old_compact = '''
def _compact_memory_if_needed() -> None:
    if not STATE.get("memory_enabled"):
        return

    messages = STATE["messages"]
    target_count = max(MAX_KEPT_HISTORY_MESSAGES + 2, 18)
    if len(messages) <= target_count:
        return

    keep_tail = MAX_KEPT_HISTORY_MESSAGES
    to_summarize = messages[:-keep_tail]
    tail = messages[-keep_tail:]
    removed_assistants = sum(1 for message in to_summarize if message.get("role") == "assistant")
    existing = STATE.get("memory_summary", "").strip()
    lines = []
    if existing:
        lines.append(existing)
    lines.append(f"\\n## Memory compacted at {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.extend(_message_summary_line(message) for message in to_summarize)
    summary = "\\n".join(lines).strip()
    STATE["memory_summary"] = _clip_for_context(summary, 12_000)
    STATE["memory_summarized_count"] = int(STATE.get("memory_summarized_count", 0)) + len(to_summarize)
    STATE["messages"] = tail
    if removed_assistants:
        STATE["tools_log"] = STATE["tools_log"][removed_assistants:]
        STATE["used_skills_log"] = STATE["used_skills_log"][removed_assistants:]
'''

new_compact = '''
def _compact_memory_if_needed() -> None:
    if not STATE.get("memory_enabled"):
        return

    messages = STATE["messages"]
    # Estimate total token/char usage
    total_chars = sum(len(str(m.get("content", ""))) for m in messages)
    
    # We trigger auto-compaction if messages get too large OR if we exceed MAX_KEPT_HISTORY_MESSAGES by a large margin
    char_limit = int(STATE.get("context_token_budget", DEFAULT_CONTEXT_TOKEN_BUDGET)) * 3 # roughly 3 chars per token threshold
    
    if len(messages) <= max(MAX_KEPT_HISTORY_MESSAGES + 2, 18) and total_chars < char_limit:
        return

    keep_tail = MAX_KEPT_HISTORY_MESSAGES
    to_summarize = messages[:-keep_tail]
    tail = messages[-keep_tail:]
    removed_assistants = sum(1 for message in to_summarize if message.get("role") == "assistant")
    existing = STATE.get("memory_summary", "").strip()
    
    print(f"Auto-compacting {len(to_summarize)} messages... (Total chars: {total_chars})")
    
    # Prepare LLM request for summarization
    system_prompt = "You are a memory compaction module. Summarize the provided conversation history. Extract and retain ALL important technical details, file paths, code structures, user preferences, and unresolved plans. Be extremely concise but comprehensive."
    user_prompt = "CONVERSATION HISTORY TO SUMMARIZE:\\n"
    if existing:
        user_prompt += f"\\n--- PREVIOUS SUMMARY ---\\n{existing}\\n"
    user_prompt += "\\n--- NEW MESSAGES ---\\n"
    for message in to_summarize:
        role = message.get("role", "unknown")
        content = _clip_for_context(message.get("content", ""), 2000) # Clip individual messages to avoid blowing up the summarization prompt
        user_prompt += f"{role}: {content}\\n\\n"
    
    try:
        # We temporarily disable tools for the summarizer
        old_tools = STATE.get("active_tools", [])
        # We don't need to change state tools if _call_model respects _active_tool_schemas, but we can't easily override it without a hack.
        # So we'll just run _call_model and ignore tool calls.
        summary_history = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        response = _call_model(summary_history)
        new_summary = response.get("content", "").strip()
        if not new_summary:
            raise Exception("LLM returned empty summary")
            
        summary = f"## Memory compacted at {time.strftime('%Y-%m-%d %H:%M:%S')}\\n{new_summary}"
    except Exception as e:
        print(f"LLM compaction failed: {e}. Falling back to basic clipping.")
        lines = []
        if existing:
            lines.append(existing)
        lines.append(f"\\n## Memory compacted at {time.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.extend(_message_summary_line(message) for message in to_summarize)
        summary = "\\n".join(lines).strip()
        
    STATE["memory_summary"] = _clip_for_context(summary, 12_000)
    STATE["memory_summarized_count"] = int(STATE.get("memory_summarized_count", 0)) + len(to_summarize)
    STATE["messages"] = tail
    if removed_assistants:
        STATE["tools_log"] = STATE["tools_log"][removed_assistants:]
        STATE["used_skills_log"] = STATE["used_skills_log"][removed_assistants:]
'''

text = text.replace(old_compact, new_compact)
path.write_text(text, 'utf-8')
print("Auto-compaction implemented in web_app.py.")
