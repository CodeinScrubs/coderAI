import pathlib

path = pathlib.Path('E:/llm_projects/agantic_ai/ollama_workspace_v4/tools.py')
text = path.read_text('utf-8')

handler_code = '''
def tool_run_command(command: str, timeout: int = 30) -> str:
    import subprocess
    try:
        ws = get_workspace()
        timeout = max(5, min(int(timeout or 30), 120))
        
        arguments = {"command": command, "timeout": timeout}
        _gate_approval("run_command", arguments, f"Execute command in {ws}:\\n{command}", "diff")
        
        # Check if the command is destructive (re-using _is_destructive_command from tools.py)
        is_dangerous, reason = _is_destructive_command(command)
        if is_dangerous:
            return f"Error: Command rejected for safety reasons: {reason}"
        
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        
        result = subprocess.run(
            command,
            shell=True,
            cwd=str(ws),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=creationflags
        )
        
        output = result.stdout
        if result.stderr:
            output += "\\n[STDERR]:\\n" + result.stderr
            
        if not output.strip():
            output = "Command executed successfully with no output."
            
        if result.returncode != 0:
            output = f"Command exited with code {result.returncode}\\n{output}"
            
        # truncate if too long
        if len(output) > 8000:
            output = output[:8000] + "\\n... [truncated]"
            
        return output
    except subprocess.TimeoutExpired:
        return f"Error: Command timed out after {timeout} seconds."
    except ToolApprovalRequired:
        raise
    except Exception as e:
        return f"Error executing command: {e}"
'''

if "def tool_run_command" not in text:
    # Insert right before tool_list_files
    text = text.replace('def tool_list_files(', handler_code + '\n\ndef tool_list_files(')
    
    # Add to _HANDLERS
    text = text.replace('"write_file":   lambda a: tool_write_file(a["path"], a["content"]),', 
                        '"write_file":   lambda a: tool_write_file(a["path"], a["content"]),\n    "run_command":  lambda a: tool_run_command(a["command"], a.get("timeout", 30)),')
    
    path.write_text(text, 'utf-8')
    print("Handler added.")
else:
    print("Handler already exists.")
