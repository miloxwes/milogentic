from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agentic_app.agent import build_agent


app = FastAPI(title="Agentic App (Minimal)")

_agent = build_agent()
WEB_DIR = Path(__file__).resolve().parent / "web"

app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")


class RunRequest(BaseModel):
    session_id: str
    goal: str


@app.get("/", response_class=FileResponse)
def home() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.post("/agent/run")
def run_agent(req: RunRequest):
    result = _agent.run(session_id=req.session_id, user_goal=req.goal)
    return {
        "session_id": result.session_id,
        "final_text": result.final_text,
        "steps": result.steps,
    }


def main() -> None:
    # Convenience entrypoint (not used by uvicorn directly).
    import uvicorn
    uvicorn.run("agentic_app.app:app", host="127.0.0.1", port=8000, reload=True)
