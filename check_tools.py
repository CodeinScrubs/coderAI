import sys
sys.path.insert(0, r"E:\llm_projects\agantic_ai\ollama_workspace_v4")
from tools import TOOL_SCHEMAS, _HANDLERS
schema_names = {s["function"]["name"] for s in TOOL_SCHEMAS}
handler_names = set(_HANDLERS.keys())
print("Missing handlers for:", schema_names - handler_names)
print("Missing schemas for:", handler_names - schema_names)
