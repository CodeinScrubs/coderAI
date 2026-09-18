import os
import glob
from pathlib import Path

def main():
    root = Path("coderai")
    for filepath in root.rglob("*.py"):
        content = filepath.read_text("utf-8")
        if "11434" in content:
            # We will use regex or string replace.
            # Many places use "http://127.0.0.1:11434"
            # Some places do os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
            
            # First normalize everything to just use config._BASE or os.getenv
            # To be safe and simple, let's just globally replace "http://127.0.0.1:11434" with a variable.
            # However, `os` might not be imported.
            
            # Let's just replace `"http://127.0.0.1:11434"` with `os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")`
            # and make sure `import os` is in the file.
            
            new_content = content.replace('"http://127.0.0.1:11434"', 'os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")')
            
            if new_content != content:
                if "import os" not in new_content:
                    new_content = "import os\n" + new_content
                filepath.write_text(new_content, "utf-8")
                print(f"Updated {filepath}")

if __name__ == "__main__":
    main()
