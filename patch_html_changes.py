import pathlib

path = pathlib.Path('E:/llm_projects/agantic_ai/ollama_workspace_v4/web_ui/index.html')
text = path.read_text('utf-8')

old_tab = '''          <nav class="tabs workspace-tabs" aria-label="Workspace panel">
            <button class="tab active" data-tab="files">Files</button>
          </nav>'''
new_tab = '''          <nav class="tabs workspace-tabs" aria-label="Workspace panel">
            <button class="tab active" data-tab="files">Files</button>
            <button class="tab" data-tab="changes">Changes</button>
          </nav>'''

old_section = '''          <section id="filesTab" class="tab-page active">'''
new_section = '''          <section id="changesTab" class="tab-page" style="display:none;">
            <div class="index-heading"><div><strong>Session Changes</strong><span>Files modified in this session</span></div></div>
            <div id="sessionChangesList" class="file-list"></div>
            <div style="padding: 1rem;">
                <button id="refreshChangesBtn" class="ghost small-btn">Refresh Changes</button>
            </div>
          </section>

          <section id="filesTab" class="tab-page active">'''

text = text.replace(old_tab, new_tab)
text = text.replace(old_section, new_section)
path.write_text(text, 'utf-8')
print("Added Changes tab to HTML")
