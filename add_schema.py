import pathlib

path = pathlib.Path('E:/llm_projects/agantic_ai/ollama_workspace_v4/tools.py')
text = path.read_text('utf-8')

schema_addition = '''    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Execute a shell command in the workspace to run tests, build the project, or check status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The command to execute (e.g., 'pytest', 'npm install')"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds (default 30, max 120)"}
                },
                "required": ["command"]
            }
        }
    },'''

# Insert the schema into TOOL_SCHEMAS
if "run_command" not in text:
    text = text.replace('TOOL_SCHEMAS = [', 'TOOL_SCHEMAS = [\n' + schema_addition)
    path.write_text(text, 'utf-8')
    print("Schema added.")
else:
    print("Schema already exists.")
