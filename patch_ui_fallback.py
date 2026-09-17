import pathlib

path = pathlib.Path('E:/llm_projects/agantic_ai/ollama_workspace_v4/web_ui/index.html')
text = path.read_text('utf-8')

old = '''          <label class="model-field-label">
            <span>Available Ollama Models</span>
            <div class="model-select-row">
              <select id="modalOllamaModelSelect" class="model-select-input"></select>
              <button id="refreshOllamaModels" type="button" class="icon-btn" aria-label="Refresh models" title="Refresh available models">?</button>
            </div>
          </label>'''

new = '''          <label class="model-field-label">
            <span>Available Ollama Models</span>
            <div class="model-select-row">
              <select id="modalOllamaModelSelect" class="model-select-input"></select>
              <button id="refreshOllamaModels" type="button" class="icon-btn" aria-label="Refresh models" title="Refresh available models">?</button>
            </div>
          </label>
          <label class="model-field-label">
            <span>Fallback Model (LiteLLM Format)</span>
            <input id="modalFallbackModel" class="model-text-input" placeholder="e.g. groq/llama3-8b-8192">
          </label>'''

text = text.replace(old, new)
path.write_text(text, 'utf-8')
print("Added fallback UI element")
