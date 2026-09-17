import pathlib

path = pathlib.Path('E:/llm_projects/agantic_ai/ollama_workspace_v4/launcher.py')
text = path.read_text('utf-8')

new_imports = '''import os
import socket
import threading
import webbrowser
import sys'''

new_main = '''def main() -> None:
    if "--cli" in sys.argv:
        import tui_app
        tui_app.main()
        return

    os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")'''

text = text.replace('import os\nimport socket\nimport threading\nimport webbrowser', new_imports)
text = text.replace('def main() -> None:\n    os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")', new_main)

path.write_text(text, 'utf-8')
print("Added --cli to launcher")
