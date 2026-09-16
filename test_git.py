import sys
sys.path.insert(0, r"E:\llm_projects\agantic_ai\ollama_workspace_v4")
from tools import set_workspace, _HANDLERS
set_workspace(r"E:\llm_projects\agantic_ai\ollama_workspace_v4")
print(_HANDLERS["git_status"]({}))
