"""FastAPI application — Phase 4 additions:
  - /api/health endpoint (used by frontend status dot)
  - session_id / thread_id for multi-turn LangGraph state
  - safe upload path (UUID prefix, extension + size validation)
  - CORS without allow_credentials so wildcard origin is valid
"""
import os
import pathlib
import uuid

import json as _json

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

from agent.graph import app as agent_app  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".mp3", ".wav", ".m4a"}
MAX_UPLOAD_MB      = int(os.getenv("MAX_UPLOAD_MB", "50"))
MAX_UPLOAD_BYTES   = MAX_UPLOAD_MB * 1024 * 1024

base       = pathlib.Path(__file__).parent.resolve()
frontend   = base.parent / "frontend"
UPLOAD_DIR = base / "temp_uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="Agentic AI Assistant")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(frontend)), name="static")


@app.get("/")
def root():
    return RedirectResponse(url="/static/index.html")


# ---------------------------------------------------------------------------
# Health (Phase 4.2) — used by frontend status dot
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "model":  os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
    }


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class ChatRequest(BaseModel):
    message:    str
    file_path:  Optional[str] = None
    session_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------
@app.post("/api/chat")
async def chat(req: ChatRequest):
    thread_id = req.session_id or str(uuid.uuid4())
    try:
        state = {
            "user_message": req.message,
            "file_path":    req.file_path,
            "plan_log":     [],   # reset logs each turn
            # chat_history intentionally omitted — MemorySaver preserves it across turns
        }
        config = {"configurable": {"thread_id": thread_id}}
        result = await agent_app.ainvoke(state, config=config)

        return {
            "response":          result.get("agent_response", ""),
            "action":            result.get("action_taken", ""),
            "extracted_content": result.get("extracted_content") or "",
            "plan":              result.get("current_plan") or "",
            "logs":              result.get("plan_log") or [],
            "session_id":        thread_id,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Chat — SSE streaming (Phase 3.3)
# ---------------------------------------------------------------------------
@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    thread_id = req.session_id or str(uuid.uuid4())

    state = {
        "user_message": req.message,
        "file_path":    req.file_path,
        "plan_log":     [],
    }
    config = {"configurable": {"thread_id": thread_id}}

    async def generate():
        streamed_any = False
        try:
            async for event in agent_app.astream_events(state, config, version="v2"):
                etype = event.get("event", "")
                node  = event.get("metadata", {}).get("langgraph_node", "")

                if etype == "on_chat_model_stream" and node == "execute":
                    chunk = event["data"].get("chunk")
                    tok = (chunk.content if chunk and hasattr(chunk, "content") else "") or ""
                    if tok:
                        streamed_any = True
                        yield f"data: {_json.dumps({'type': 'token', 'content': tok})}\n\n"

            # Retrieve final checkpoint state for metadata
            snap = await agent_app.aget_state(config)
            vals = snap.values if hasattr(snap, "values") else {}

            # Clarify path — no tokens were streamed; send full response as one burst
            if not streamed_any:
                resp_text = vals.get("agent_response", "")
                if resp_text:
                    yield f"data: {_json.dumps({'type': 'token', 'content': resp_text})}\n\n"

            yield f"data: {_json.dumps({'type': 'done', 'action': vals.get('action_taken', ''), 'extracted_content': vals.get('extracted_content') or '', 'plan': vals.get('current_plan') or '', 'logs': vals.get('plan_log') or [], 'session_id': thread_id})}\n\n"

        except Exception as exc:
            yield f"data: {_json.dumps({'type': 'error', 'content': str(exc)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":    "no-cache",
            "X-Accel-Buffering": "no",
            "Connection":       "keep-alive",
        },
    )


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------
@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    suffix = pathlib.Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"File type '{suffix}' not supported. "
                   f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the {MAX_UPLOAD_MB} MB limit.",
        )

    safe_name   = pathlib.Path(file.filename or "upload").name
    unique_name = f"{uuid.uuid4().hex[:8]}_{safe_name}"
    dest        = UPLOAD_DIR / unique_name
    dest.write_bytes(data)

    return {
        "filename":     safe_name,
        "filepath":     str(dest.resolve()),
        "content_type": file.content_type,
        "size_bytes":   len(data),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
