from __future__ import annotations

import json
import os

from dataclasses import dataclass
from typing import Any, Dict, List

from agentic_app.llm_stub import LLMStub, LLMResponse
from agentic_app.memory import MemoryStore
from agentic_app.rate_limit import InMemoryRateLimiter
from agentic_app.tools import Tool, build_tools, tool_spec
from agentic_app.llm_groq import GroqLLM



@dataclass(frozen=True)
class AgentResult:
    session_id: str
    final_text: str
    steps: List[Dict[str, Any]]


class Agent:
    def __init__(
        self,
        memory: MemoryStore,
        llm: LLMStub,
        tools: List[Tool],
        rate_limiter: InMemoryRateLimiter,
    ) -> None:
        self.memory = memory
        self.llm = llm
        self.tools = {t.name: t for t in tools}
        self.rate_limiter = rate_limiter

    def _rag_retrieve(self, user_goal: str) -> str:
        # Replace with vector DB retrieval later.
        return "User preferences: prefer direct flights, avoid redeye when possible."

    def run(self, session_id: str, user_goal: str, max_iters: int = 20) -> AgentResult:
        self.memory.add_event(session_id, "user", user_goal)

        steps: List[Dict[str, Any]] = []
        for iteration in range(1, max_iters + 1):
            events = self.memory.get_recent(session_id, limit=100)
            rag_context = self._rag_retrieve(user_goal)
            tool_specs = [tool_spec(t) for t in self.tools.values()]
            memory_for_llm = [{"role": e.role, "content": e.content, "meta": e.meta} for e in events]
            steps.append(
                {
                    "type": "llm_prompt",
                    "iteration": iteration,
                    "prompt": {
                        "user_goal": user_goal,
                        "memory_events": memory_for_llm,
                        "tools": tool_specs,
                        "rag_context": rag_context,
                    },
                }
            )

            llm_resp: LLMResponse = self.llm.decide(
                user_goal=user_goal,
                memory_events=memory_for_llm,
                tools=tool_specs,
                rag_context=rag_context,
            )
            steps.append(
                {
                    "type": "llm_result",
                    "iteration": iteration,
                    "result": {
                        "tool_call": (
                            {
                                "tool_name": llm_resp.tool_call.tool_name,
                                "arguments": llm_resp.tool_call.arguments,
                            }
                            if llm_resp.tool_call
                            else None
                        ),
                        "final_text": llm_resp.final_text,
                    },
                }
            )

            if llm_resp.final_text:
                self.memory.add_event(session_id, "llm", llm_resp.final_text)
                steps.append({"type": "final", "text": llm_resp.final_text})
                return AgentResult(session_id=session_id, final_text=llm_resp.final_text, steps=steps)

            if not llm_resp.tool_call:
                txt = "LLM returned neither a tool call nor final text. Stopping."
                self.memory.add_event(session_id, "agent", txt)
                steps.append({"type": "error", "text": txt})
                return AgentResult(session_id=session_id, final_text=txt, steps=steps)

            tool_name = llm_resp.tool_call.tool_name
            args = llm_resp.tool_call.arguments

            tool = self.tools.get(tool_name)
            if not tool:
                msg = f"Unknown tool requested: {tool_name}"
                self.memory.add_event(session_id, "agent", msg, meta={"requested_args": args})
                steps.append({"type": "error", "text": msg, "tool": tool_name})
                return AgentResult(session_id=session_id, final_text=msg, steps=steps)

            # Safety: booking requires explicit approval.
            if tool_name == "confirm_booking" and not args.get("user_approved", False):
                msg = "Blocked confirm_booking: requires user_approved=true."
                self.memory.add_event(session_id, "agent", msg, meta={"requested_args": args})
                steps.append({"type": "blocked", "tool": tool_name, "reason": msg})
                return AgentResult(session_id=session_id, final_text=msg, steps=steps)

            # Rate limiting
            if tool.rate_limit:
                allowed = self.rate_limiter.allow(session_id, tool_name, tool.rate_limit)
                if not allowed:
                    msg = f"Rate limit exceeded for tool={tool_name}. Try again later or reduce calls."
                    self.memory.add_event(session_id, "agent", msg)
                    steps.append({"type": "rate_limited", "tool": tool_name})
                    return AgentResult(session_id=session_id, final_text=msg, steps=steps)

            self.memory.add_event(
                session_id,
                "llm",
                f"Calling tool: {tool_name}({json.dumps(args)})",
                meta={"tool_name": tool_name, "tool_args": args},
            )

            try:
                result = tool.handler(args)
            except Exception as e:
                msg = f"Tool execution failed: {tool_name}: {e}"
                self.memory.add_event(session_id, "agent", msg)
                steps.append({"type": "tool_error", "tool": tool_name, "error": str(e)})
                return AgentResult(session_id=session_id, final_text=msg, steps=steps)

            self.memory.add_event(
                session_id,
                "tool",
                f"{tool_name} returned result",
                meta={"tool_name": tool_name, "tool_result": result},
            )
            steps.append({"type": "tool_result", "tool": tool_name, "result": result})

        msg = f"Max iterations ({max_iters}) reached without completion."
        self.memory.add_event(session_id, "agent", msg)
        return AgentResult(session_id=session_id, final_text=msg, steps=steps)



# def build_agent(db_path: str = "memory.db") -> Agent:
#     memory = MemoryStore(db_path=db_path)
#     llm = LLMStub()
#     tools = build_tools()
#     limiter = InMemoryRateLimiter()
#     return Agent(memory=memory, llm=llm, tools=tools, rate_limiter=limiter)

def build_agent(db_path: str = "memory.db") -> Agent:
    memory = MemoryStore(db_path=db_path)

    if os.environ.get("GROQ_API_KEY"):
        llm = GroqLLM()
    else:
        llm = LLMStub()

    tools = build_tools()
    limiter = InMemoryRateLimiter()
    return Agent(memory=memory, llm=llm, tools=tools, rate_limiter=limiter)
