import pathlib

path = pathlib.Path('E:/llm_projects/agantic_ai/ollama_workspace_v4/web_ui/app.js')
text = path.read_text('utf-8')

new_logic = '''
  refreshChangesBtn?.addEventListener("click", refreshSessionChanges);
'''

# We can append it to the init function or just at the end.
if "refreshChangesBtn" not in text:
    text += new_logic
    path.write_text(text, 'utf-8')
    print("Added event listener")
else:
    print("Already added")
