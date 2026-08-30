"""
fastapi_app.py - Modern FastAPI server with non-blocking StreamingResponse, WebSocket (/ws/chat) and Abort/Cancel support.
"""

from __future__ import annotations

import asyncio
import json
import os
import queue
import threading
from pathlib import Path
from typing import Any, AsyncGenerator

import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

import web_app
from codebase_index import CodebaseIndex
from tools import cancel_current_execution, get_workspace, set_workspace


def create_app() -> FastAPI:
    app = FastAPI(title="CoderAI Workspace API", version="2.0.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    static_dir = Path(web_app.STATIC_DIR).resolve()
    static_dir.mkdir(exist_ok=True)

    @app.get("/")
    async def index():
        index_file = static_dir / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file), media_type="text/html")
        return HTMLResponse("<h1>CoderAI Web UI is ready</h1>")

    @app.get("/api/state")
    @app.get("/api/settings")
    async def get_state(request: Request):
        sid = request.headers.get("x-session-id") or request.query_params.get("session_id")
        return web_app._client_state(sid)

    @app.post("/api/settings")
    async def save_settings(request: Request):
        data = await request.json()
        requested_mode = data.get("conn_mode", web_app.STATE["conn_mode"])
        for key in (
            "conn_mode", "temperature", "enable_thinking",
            "custom_api_url", "custom_api_key", "custom_api_model", "memory_enabled",
            "context_token_budget", "response_token_budget", "auto_continue",
            "tavily_enabled", "tavily_api_key",
            "git_approval_mode",
            "smart_skill_confirmation",
            "sandbox_mode", "sandbox_docker_image",
        ):
            if key in data:
                web_app.STATE[key] = data[key]
        if requested_mode == web_app.MODE_LOCAL and "model" in data:
            web_app.STATE["model"] = str(data.get("model") or web_app.STATE["model"]).strip()
        elif requested_mode == web_app.MODE_CUSTOM and not str(web_app.STATE.get("custom_api_model") or "").strip():
            web_app.STATE["custom_api_model"] = str(data.get("model") or "gpt-4o-mini").strip()
        web_app.STATE["custom_api_model"] = str(web_app.STATE.get("custom_api_model") or "gpt-4o-mini").strip()
        if "tavily_api_key" in data:
            web_app.STATE["tavily_api_key"] = str(data.get("tavily_api_key") or "").strip()
        if not web_app.STATE.get("tavily_enabled"):
            web_app.STATE["tavily_api_key"] = ""
        web_app._sync_tool_settings()
        for key in ("context_token_budget", "response_token_budget"):
            if key in web_app.STATE:
                web_app.STATE[key] = max(512, int(web_app.STATE[key]))
        if requested_mode == web_app.MODE_LOCAL and "model" in data:
            web_app.STATE["model_user_selected"] = True
        web_app._save_persisted_settings()
        return web_app._client_state()

    @app.get("/api/models")
    async def get_models():
        return web_app._available_models()

    @app.get("/api/projects")
    async def get_projects():
        return {"projects": web_app._project_cards()}

    @app.get("/api/prompts")
    async def get_prompts():
        return web_app._prompt_payload()

    @app.get("/api/skills")
    async def get_skills():
        return {"skills": web_app._skills_payload()}

    @app.get("/api/skills/diagnostics")
    async def get_skills_diagnostics():
        return web_app._skills_diagnostics()

    @app.get("/api/skills/usage")
    async def get_skills_usage():
        return web_app._skill_usage_payload()

    @app.post("/api/cancel")
    async def cancel_execution():
        killed = cancel_current_execution()
        web_app.STATE["agent_running"] = False
        return {
            "ok": True,
            "cancelled": True,
            "process_killed": killed,
            "state": web_app._client_state(),
        }

    @app.post("/api/project/delete")
    @app.delete("/api/project")
    async def delete_project(request: Request):
        data = await request.json()
        manager = web_app._memory_manager()
        project_id = data.get("project_id")
        workspace_path = data.get("workspace_path")
        deleted = False
        if project_id is not None:
            deleted = manager.delete_project_by_id(int(project_id))
        elif workspace_path:
            deleted = manager.delete_project_by_path(str(workspace_path))
        return {
            "ok": True,
            "deleted": deleted,
            "projects": web_app._project_cards(manager),
        }

    @app.post("/api/workspace")
    async def activate_workspace(request: Request):
        data = await request.json()
        path = data.get("path", "")
        ok, msg = web_app._activate_workspace_memory(path)
        if not ok:
            raise HTTPException(status_code=400, detail=msg)
        return {"ok": ok, "message": msg, "workspace": web_app._workspace_snapshot()}

    @app.post("/api/chat")
    async def chat(request: Request):
        data = await request.json()
        prompt = data.get("prompt", "")
        context = data.get("active_context")
        return web_app._run_agent(prompt, context)

    @app.post("/api/chat_stream")
    async def chat_stream(request: Request):
        data = await request.json()
        prompt = data.get("prompt", "")
        context = data.get("active_context")

        async def event_generator() -> AsyncGenerator[str, None]:
            web_app.STATE["agent_running"] = True
            q: queue.Queue = queue.Queue()

            def thread_sink(ev: dict):
                q.put(ev)

            def worker():
                try:
                    web_app._run_agent_stream(prompt, thread_sink, context)
                finally:
                    q.put(None)

            thread = threading.Thread(target=worker, daemon=True)
            thread.start()

            try:
                while True:
                    try:
                        ev = q.get_nowait()
                        if ev is None:
                            break
                        yield json.dumps(ev, default=web_app._json_default) + "\n"
                    except queue.Empty:
                        if not thread.is_alive() and q.empty():
                            break
                        await asyncio.sleep(0.01)
            finally:
                web_app.STATE["agent_running"] = False

        return StreamingResponse(event_generator(), media_type="application/x-ndjson")

    # ══════════════════════════════════════════════════════════════════════════════
    # ── WebSocket Real-Time Chat & Thinking Logs
    # ══════════════════════════════════════════════════════════════════════════════
    @app.websocket("/ws/chat")
    async def websocket_chat(websocket: WebSocket):
        await websocket.accept()
        loop = asyncio.get_running_loop()

        try:
            while True:
                msg_text = await websocket.receive_text()
                data = json.loads(msg_text)
                action = data.get("type", "chat")
                sid = websocket.query_params.get("session_id") or data.get("session_id")

                if action == "cancel":
                    cancel_current_execution()
                    web_app.STATE["agent_running"] = False
                    await websocket.send_text(json.dumps({
                        "type": "cancelled",
                        "state": web_app._client_state(sid),
                    }))

                elif action == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))

                elif action == "chat":
                    prompt = data.get("prompt", "")
                    context = data.get("active_context")
                    web_app.STATE["agent_running"] = True

                    def sink(ev: dict):
                        try:
                            asyncio.run_coroutine_threadsafe(
                                websocket.send_text(json.dumps(ev, default=web_app._json_default)),
                                loop,
                            )
                        except Exception:
                            pass

                    def run_worker():
                        try:
                            web_app._run_agent_stream(prompt, sink, context)
                        finally:
                            try:
                                asyncio.run_coroutine_threadsafe(
                                    websocket.send_text(json.dumps({"type": "done", "state": web_app._client_state(sid)}, default=web_app._json_default)),
                                    loop,
                                )
                            except Exception:
                                pass

                    await loop.run_in_executor(None, run_worker)
                    web_app.STATE["agent_running"] = False

        except (WebSocketDisconnect, Exception):
            cancel_current_execution()
            web_app.STATE["agent_running"] = False

    # Mount static assets
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    return app


app = create_app()


def main():
    host = os.getenv("WEB_APP_HOST", "127.0.0.1")
    port = int(os.getenv("WEB_APP_PORT", "7864"))
    print(f"Starting CoderAI FastAPI server on http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
