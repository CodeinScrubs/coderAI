import pathlib

path = pathlib.Path('E:/llm_projects/agantic_ai/ollama_workspace_v4/web_ui/app.js')
text = path.read_text('utf-8')

old = '''  const apiUrl = (modalCustomApiUrl?.value?.trim() || customApiUrl?.value?.trim() || state.data?.settings?.custom_api_url || "https://api.openai.com/v1");
  const apiKey = (modalCustomApiKey?.value?.trim() || customApiKey?.value?.trim() || "");
  const customApiModel = (modalCustomApiModel?.value?.trim() || customApiModel?.value?.trim() || state.data?.settings?.custom_api_model || "gpt-4o-mini");'''

new = '''  const apiUrl = customApiUrl?.value?.trim() || state.data?.settings?.custom_api_url || "https://api.openai.com/v1";
  const apiKey = customApiKey?.value?.trim() || "";
  const customApiModel = customApiModel?.value?.trim() || state.data?.settings?.custom_api_model || "gpt-4o-mini";'''

text = text.replace(old, new)
path.write_text(text, 'utf-8')
print("Fixed settings precedence in app.js")
