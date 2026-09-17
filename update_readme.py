import pathlib

path = pathlib.Path('E:/llm_projects/agantic_ai/ollama_workspace_v4/README.md')
text = path.read_text('utf-8')

new_features = '''
## OpenCode Integration Features

CoderAI has been heavily upgraded to include key features inspired by OpenCode:

1. **Terminal Command Execution (un_command)**: The agent can run arbitrary CLI commands, unit tests, and build scripts.
2. **Robust Fuzzy File Replacement**: The eplace_in_file tool uses an advanced fuzzy-search algorithm to reliably replace code blocks even when the LLM makes indentation or whitespace errors.
3. **Context Auto-Compaction**: When the conversation history grows too large, the LLM automatically summarizes the chat in the background, preventing context window exhaustion and "forgetting".
4. **Native Diagnostics (Compiler Brain)**: After editing any Python file, the agent automatically runs an AST-based syntax checker (check_file_diagnostics) to catch and fix syntax errors instantly before answering the user.
'''

if "OpenCode Integration Features" not in text:
    text = text.replace('## Plan Mode', new_features + '\n## Plan Mode')
    path.write_text(text, 'utf-8')
    print("Added features to README")
else:
    print("Already added to README")
