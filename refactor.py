import os
import re
import shutil
from pathlib import Path

# Mapping of file module name to target package path
MODULE_MAPPING = {
    "config": "coderai.core.config",
    "agent_runtime": "coderai.core.agent_runtime",
    "prompt_manager": "coderai.core.prompt_manager",
    "session_manager": "coderai.core.session_manager",
    "context_builder": "coderai.core.context_builder",
    "tools": "coderai.tools.tools",
    "advanced_tools": "coderai.tools.advanced_tools",
    "tool_parser": "coderai.tools.tool_parser",
    "sandbox_runner": "coderai.tools.sandbox_runner",
    "terminal_manager": "coderai.tools.terminal_manager",
    "memory_manager": "coderai.memory.memory_manager",
    "memory_graph": "coderai.memory.memory_graph",
    "vector_store": "coderai.memory.vector_store",
    "hindsight_manager": "coderai.memory.hindsight_manager",
    "codebase_index": "coderai.codebase.codebase_index",
    "code_graph_service": "coderai.codebase.code_graph_service",
    "syntax_chunker": "coderai.codebase.syntax_chunker",
    "workspace_filter": "coderai.codebase.workspace_filter",
    "git_manager": "coderai.codebase.git_manager",
    "project_intelligence": "coderai.codebase.project_intelligence",
    "skill_router": "coderai.skills.skill_router",
    "skill_tracker": "coderai.skills.skill_tracker",
    "skills_manager": "coderai.skills.skills_manager",
    "web_app": "coderai.server.web_app",
    "fastapi_app": "coderai.server.fastapi_app",
    "tui_app": "coderai.server.tui_app",
    "launcher": "coderai.server.launcher",
    "approval_policy": "coderai.utils.approval_policy"
}

def setup_directories(root_dir: Path):
    packages = set(".".join(p.split(".")[:-1]) for p in MODULE_MAPPING.values())
    for pkg in packages:
        pkg_path = root_dir.joinpath(*pkg.split("."))
        pkg_path.mkdir(parents=True, exist_ok=True)
        # Create __init__.py up the tree
        curr = pkg_path
        while curr != root_dir:
            init_file = curr / "__init__.py"
            if not init_file.exists():
                init_file.write_text("")
            curr = curr.parent

def rewrite_imports(content: str) -> str:
    # We need to replace:
    # 1. import X -> from pkg import X (if X is in mapping, otherwise leave alone)
    # 2. import X.Y is not used much locally, but handle just in case
    # 3. from X import Y -> from pkg.X import Y (if X is in mapping)
    
    # Sort modules by length descending to prevent partial replacements (e.g. tools vs advanced_tools)
    modules = sorted(list(MODULE_MAPPING.keys()), key=len, reverse=True)
    
    for mod in modules:
        full_pkg = MODULE_MAPPING[mod]
        # match `import X` or `import X as Y`
        # Using regex to ensure word boundaries
        
        # Replace `from X import`
        content = re.sub(rf"^(\s*)from\s+{mod}\s+import\s+", rf"\1from {full_pkg} import ", content, flags=re.MULTILINE)
        
        # Replace `import X`
        # Because we replace `import X` with `from pkg import X`, we need to make sure we don't break `X.function()`
        # Wait, if we do `from pkg import X`, then `X.function()` still works exactly the same!
        # Example: `import web_app` -> `from coderai.server import web_app`. Then `web_app.main()` works!
        # Let's match `import X` but ignore `from Y import X`
        def import_replacer(match):
            indent = match.group(1)
            rest = match.group(2) # "X", "X as Z", "X, A, B"
            # If it's a multi-import like `import X, Y`, it's complicated.
            # In python, usually people put them on separate lines.
            # We'll split the modules and rewrite them.
            parts = [p.strip() for p in rest.split(",")]
            new_lines = []
            for p in parts:
                mod_name = p.split(" ")[0]
                if mod_name in MODULE_MAPPING:
                    new_lines.append(f"{indent}from {'.'.join(MODULE_MAPPING[mod_name].split('.')[:-1])} import {p}")
                else:
                    new_lines.append(f"{indent}import {p}")
            return "\n".join(new_lines)
            
        content = re.sub(rf"^(\s*)import\s+({mod}(?:\s+as\s+\w+)?(?:,\s*\w+(?:\s+as\s+\w+)?)*)(?=\s|$)", import_replacer, content, flags=re.MULTILINE)
        
    return content

def main():
    root = Path(".")
    
    # 1. Setup directories
    setup_directories(root)
    print("Created directory structures.")
    
    # 2. Process each file
    for mod_name, full_pkg in MODULE_MAPPING.items():
        old_file = root / f"{mod_name}.py"
        if not old_file.exists():
            print(f"Skipping {mod_name}.py, not found.")
            continue
            
        new_file = root.joinpath(*full_pkg.split("."))
        new_file = new_file.with_suffix(".py")
        
        content = old_file.read_text("utf-8")
        new_content = rewrite_imports(content)
        
        new_file.write_text(new_content, "utf-8")
        old_file.unlink() # Delete old file
        print(f"Moved {old_file} -> {new_file}")

if __name__ == "__main__":
    main()
