import pathlib

path = pathlib.Path('E:/llm_projects/agantic_ai/ollama_workspace_v4/web_app.py')
text = path.read_text('utf-8')

old = '''            "category": s.category,
            "triggers": s.triggers or [],
            "disabled": s.disable_model_invocation,
        }
        for s in sm.all()'''

new = '''            "category": s.category,
            "triggers": s.triggers or [],
            "disabled": s.disable_model_invocation,
            "content": s.content,
        }
        for s in sm.all()'''

if '"content": s.content' not in text:
    text = text.replace(old, new)
    path.write_text(text, 'utf-8')
    print("Added content to payload")
else:
    print("Already added")
