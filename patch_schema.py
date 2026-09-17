import pathlib
import json

path = pathlib.Path('E:/llm_projects/agantic_ai/ollama_workspace_v4/tools.py')
text = path.read_text('utf-8')

diagnostics_schema = '''    {
        "type": "function",
        "function": {
            "name": "check_file_diagnostics",
            "description": "Check a file for syntax errors and warnings (LSP-like diagnostics). Always run this after editing a file to ensure your code is correct.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the file to check"}
                },
                "required": ["path"]
            }
        }
    },
'''

if "check_file_diagnostics" not in text:
    text = text.replace('TOOL_SCHEMAS: list[dict] = [\n', 'TOOL_SCHEMAS: list[dict] = [\n' + diagnostics_schema)
    path.write_text(text, 'utf-8')
    print("Injected schema")
else:
    print("Schema already exists")

