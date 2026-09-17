import pathlib
path = pathlib.Path('E:/llm_projects/agantic_ai/ollama_workspace_v4/web_ui/app.js')
text = path.read_text('utf-8')

# Fix saveSettings precedence
text = text.replace(
    'const apiUrl = (modalCustomApiUrl?.value?.trim() || customApiUrl?.value?.trim() || state.data?.settings?.custom_api_url || "https://api.openai.com/v1");',
    'const apiUrl = (customApiUrl?.value?.trim() || state.data?.settings?.custom_api_url || "https://api.openai.com/v1");'
)
text = text.replace(
    'const apiKey = (modalCustomApiKey?.value?.trim() || customApiKey?.value?.trim() || "");',
    'const apiKey = (customApiKey?.value?.trim() || "");'
)
text = text.replace(
    'const customApiModel = (modalCustomApiModel?.value?.trim() || customApiModel?.value?.trim() || state.data?.settings?.custom_api_model || "gpt-4o-mini");',
    'const customApiModel = (customApiModel?.value?.trim() || state.data?.settings?.custom_api_model || "gpt-4o-mini");'
)

# Make sure fallback_model is sent in saveSettings!
if 'fallback_model: modalFallbackModel?.value?.trim(),' not in text:
    text = text.replace(
        'custom_api_model: customApiModel,',
        'custom_api_model: customApiModel,\n      fallback_model: modalFallbackModel?.value?.trim(),'
    )

path.write_text(text, 'utf-8')
print("Successfully patched app.js")
