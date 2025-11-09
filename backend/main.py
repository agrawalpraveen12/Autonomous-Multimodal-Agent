import os, pathlib
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from typing import Optional

load_dotenv()

from agent.graph import app as agent_app

base = pathlib.Path(__file__).parent.resolve()
frontend = base.parent / "frontend"

app = FastAPI(title="Agentic AI Assistant")

@app.get("/")
def root():
    return RedirectResponse(url="/static/index.html")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

app.mount("/static", StaticFiles(directory=str(frontend)), name="static")


class ChatRequest(BaseModel):
    message: str
    file_path: Optional[str] = None


@app.post("/api/chat")
async def chat(req: ChatRequest):
    try:
        state = {
            "user_message": req.message,
            "file_path": req.file_path,
            "chat_history": []
        }
        result = await agent_app.ainvoke(state)
        return {
            "response": result.get("agent_response"),
            "action": result.get("action_taken"),
            "extracted_content": result.get("extracted_content")
        }
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    try:
        folder = "temp_uploads"
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, file.filename)

        with open(path, "wb") as f:
            f.write(await file.read())

        return {
            "filename": file.filename,
            "filepath": os.path.abspath(path),
            "content_type": file.content_type
        }
    except Exception as e:
        raise HTTPException(500, str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
