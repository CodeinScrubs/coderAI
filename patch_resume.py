import pathlib
path = pathlib.Path('E:/llm_projects/agantic_ai/ollama_workspace_v4/web_ui/app.js')
text = path.read_text('utf-8')

old_resume = '''async function resumeProjectSession(sessionId) {
  renderState(await api("/api/memory/session/resume", { method: "POST", body: JSON.stringify({ session_id: sessionId }) }));
  showWorkbench(); setActiveActivity("Agent");
}'''

new_resume = '''async function resumeProjectSession(sessionId) {
  renderState(await api("/api/memory/session/resume", { method: "POST", body: JSON.stringify({ session_id: sessionId }) }));
  showWorkbench(); 
  setActiveActivity("Agent");
  activateTab("chat");
  if (promptInput) promptInput.focus();
}'''
text = text.replace(old_resume, new_resume)

old_mem = '''async function resumeMemorySession() {
  const sessionId = resumeMemorySession.dataset.sessionId;
  if (!sessionId) return;
  renderState(await api("/api/memory/session/resume", { method: "POST", body: JSON.stringify({ session_id: sessionId }) }));
}'''

new_mem = '''async function resumeMemorySession() {
  const sessionId = resumeMemorySession.dataset.sessionId;
  if (!sessionId) return;
  renderState(await api("/api/memory/session/resume", { method: "POST", body: JSON.stringify({ session_id: sessionId }) }));
  showWorkbench();
  setActiveActivity("Agent");
  activateTab("chat");
  if (promptInput) promptInput.focus();
}'''
text = text.replace(old_mem, new_mem)

path.write_text(text, 'utf-8')
