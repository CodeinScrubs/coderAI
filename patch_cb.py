import json
from pathlib import Path

cb_path = Path("E:/llm_projects/agantic_ai/ollama_workspace_v4/context_builder.py")
content = cb_path.read_text("utf-8")

new_func = """
def summarize_chat_history_with_llm(messages: list[dict], model: str = "") -> str:
    \"\"\"Summarizes older chat messages using the LLM to save context space.\"\"\"
    try:
        from agent_runtime import AgentRuntime, RuntimeSettings
        
        # Combine messages into a single text block
        text_block = "\\n".join([f"{m.get('role', 'unknown')}: {m.get('content', '')}" for m in messages])
        
        prompt = (
            "You are a memory compaction system. Summarize the following conversation history.\\n"
            "Keep important context, code changes, user preferences, and unresolved issues.\\n"
            "Format the output as a brief, bulleted summary.\\n\\n"
            "CONVERSATION HISTORY:\\n" + text_block
        )
        
        runtime = AgentRuntime()
        settings = RuntimeSettings(model=model, temperature=0.3, max_tokens=500)
        
        # Using a direct LLM call
        response = runtime.invoke([{"role": "user", "content": prompt}], tools=[], settings=settings)
        summary = response.get("content", "").strip()
        
        if not summary:
            return "History summarized (no important details extracted)."
        return summary
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"History compaction failed: {e}"
"""

if "def summarize_chat_history_with_llm" not in content:
    content += "\n" + new_func
    cb_path.write_text(content, "utf-8")
    print("Added summarize_chat_history_with_llm to context_builder.py")
