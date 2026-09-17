import pathlib

path = pathlib.Path('E:/llm_projects/agantic_ai/ollama_workspace_v4/web_ui/app.js')
text = path.read_text('utf-8')

# 1. Update saveSettings()
old_save = '''    const customApiModel = (modalCustomApiModel?.value?.trim() || customApiModel?.value?.trim() || state.data?.settings?.custom_api_model || "gpt-4o-mini");

    const payload = {'''
new_save = '''    const customApiModel = (modalCustomApiModel?.value?.trim() || customApiModel?.value?.trim() || state.data?.settings?.custom_api_model || "gpt-4o-mini");
    const fallbackModel = (modalFallbackModel?.value?.trim() || state.data?.settings?.fallback_model || "");

    const payload = {
      fallback_model: fallbackModel,'''
text = text.replace(old_save, new_save)

# 2. Update initUI() where modalCustomApiModel is populated
old_init = '''if (modalCustomApiModel) modalCustomApiModel.value = settings.custom_api_model || "gpt-4o-mini";'''
new_init = '''if (modalCustomApiModel) modalCustomApiModel.value = settings.custom_api_model || "gpt-4o-mini";
  if (modalFallbackModel) modalFallbackModel.value = settings.fallback_model || "";'''
text = text.replace(old_init, new_init)

path.write_text(text, 'utf-8')
print("Added fallback to app.js")
