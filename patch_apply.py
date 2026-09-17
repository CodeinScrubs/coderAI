import pathlib

path = pathlib.Path('E:/llm_projects/agantic_ai/ollama_workspace_v4/web_ui/app.js')
text = path.read_text('utf-8')

old = '''  applyCustomApi?.addEventListener("click", async () => {
    const url = modalCustomApiUrl?.value?.trim() || "https://api.openai.com/v1";
    const key = modalCustomApiKey?.value?.trim() || "";
    const model = modalCustomApiModel?.value?.trim() || "gpt-4o-mini";

    if (connMode) connMode.value = "?? Custom API";
    if (customApiUrl) customApiUrl.value = url;
    if (customApiModel) customApiModel.value = model;
    if (modelSelect) modelSelect.value = model;

    closeChooseModelModal();

    const payload = {
      conn_mode: "?? Custom API",
      custom_api_url: url,
      custom_api_model: model,
      model: model,'''

new = '''  applyCustomApi?.addEventListener("click", async () => {
    const url = modalCustomApiUrl?.value?.trim() || "https://api.openai.com/v1";
    const key = modalCustomApiKey?.value?.trim() || "";
    const model = modalCustomApiModel?.value?.trim() || "gpt-4o-mini";
    const fallback = modalFallbackModel?.value?.trim() || "";

    if (connMode) connMode.value = "?? Custom API";
    if (customApiUrl) customApiUrl.value = url;
    if (customApiModel) customApiModel.value = model;
    if (modelSelect) modelSelect.value = model;

    closeChooseModelModal();

    const payload = {
      conn_mode: "?? Custom API",
      custom_api_url: url,
      custom_api_model: model,
      model: model,
      fallback_model: fallback,'''

if 'fallback_model: fallback' not in text:
    text = text.replace(old, new)
    path.write_text(text, 'utf-8')
    print("Added fallback to applyCustomApi")
