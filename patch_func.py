import pathlib

path = pathlib.Path('E:/llm_projects/agantic_ai/ollama_workspace_v4/tools.py')
text = path.read_text('utf-8')

diagnostics_func = '''
def tool_check_file_diagnostics(path: str) -> str:
    try:
        p = _safe_path(path)
        if not p.exists():
            return f"File does not exist: {path}"
            
        ext = p.suffix.lower()
        if ext == '.py':
            # 1. Native AST syntax check (super fast, catches syntax/indentation errors)
            import ast
            try:
                ast.parse(p.read_text("utf-8"))
            except SyntaxError as e:
                return f"SyntaxError in {path} at line {e.lineno}, column {e.offset}: {e.msg}\\nLine: {e.text}"
            except Exception as e:
                return f"Parse Error: {e}"
                
            # 2. Try running flake8 or pylint if installed
            import subprocess
            try:
                res = subprocess.run(["flake8", str(p)], capture_output=True, text=True, timeout=5)
                if res.returncode != 0 and res.stdout:
                    return f"Linting Warnings/Errors:\\n{res.stdout[:2000]}"
            except FileNotFoundError:
                pass # flake8 not installed
                
            return f"No syntax errors found in {path}. Code is syntactically valid."
            
        elif ext in ['.js', '.ts', '.jsx', '.tsx']:
            import subprocess
            try:
                # Try node-based syntax check or eslint
                res = subprocess.run(["node", "--check", str(p)], capture_output=True, text=True, timeout=5)
                if res.returncode != 0:
                    return f"Syntax Error:\\n{res.stderr[:2000]}"
                return f"No syntax errors found in {path}."
            except FileNotFoundError:
                return "Node.js not installed, cannot verify JS/TS syntax."
                
        else:
            return f"Diagnostics not supported natively for extension {ext}. Use tool_run_command with an appropriate linter/compiler."
            
    except Exception as e:
        return f"Error running diagnostics: {e}"
'''

if "def tool_check_file_diagnostics" not in text:
    text = text.replace('def tool_run_command(', diagnostics_func + '\ndef tool_run_command(')
    path.write_text(text, 'utf-8')
    print("Injected tool_check_file_diagnostics")
else:
    print("Function already exists")

