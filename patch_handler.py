import pathlib

path = pathlib.Path('E:/llm_projects/agantic_ai/ollama_workspace_v4/tools.py')
text = path.read_text('utf-8')

old_run = '"run_command":  lambda a: tool_run_command(a["command"], a.get("timeout", 30)),'
new_run = '"run_command":  lambda a: tool_run_command(a["command"], a.get("timeout", 30)),\n    "check_file_diagnostics": lambda a: tool_check_file_diagnostics(a["path"]),'

if "check_file_diagnostics" not in text.split("run_command")[1]:
    text = text.replace(old_run, new_run)
    path.write_text(text, 'utf-8')
    print("Injected into _HANDLERS")
else:
    print("Already in _HANDLERS")

