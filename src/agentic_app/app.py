from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from agentic_app.agent import build_agent


app = FastAPI(title="Agentic App (Minimal)")

_agent = build_agent()


class RunRequest(BaseModel):
    session_id: str
    goal: str


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
