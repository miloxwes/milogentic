from __future__ import annotations

import json
import os
from datetime import date, datetime

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
        fallback_llm: LLMStub | None = None,
    ) -> None:
        self.memory = memory
        self.llm = llm
        self.fallback_llm = fallback_llm
        self.tools = {t.name: t for t in tools}
        self.rate_limiter = rate_limiter

    def _rag_retrieve(self, user_goal: str) -> str:
        # Replace with vector DB retrieval later.
        return "User preferences: prefer direct flights, avoid redeye when possible."

    def _parse_date_field(self, value: Any) -> date | None:
        raw = str(value).strip()
        if not raw:
            return None
        try:
            return date.fromisoformat(raw)
        except ValueError:
            pass
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(raw).date()
        except ValueError:
            return None

    def _validate_flight_search_args(self, args: Dict[str, Any]) -> str | None:
        depart_raw = args.get("depart_date")
        if not depart_raw:
            return "Missing required depart_date."
        depart_date = self._parse_date_field(depart_raw)
        if depart_date is None:
            return "Invalid depart_date format. Use YYYY-MM-DD."
        args["depart_date"] = depart_date.isoformat()

        today = date.today()
        if depart_date < today:
            return f"depart_date {depart_date.isoformat()} is in the past (today is {today.isoformat()})."

        return_raw = args.get("return_date")
        if not return_raw:
            return None

        return_date = self._parse_date_field(return_raw)
        if return_date is None:
            args.pop("return_date", None)
            return None
        args["return_date"] = return_date.isoformat()

        if return_date < depart_date:
            args.pop("return_date", None)
            return None
        return None

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

            try:
                llm_resp: LLMResponse = self.llm.decide(
                    user_goal=user_goal,
                    memory_events=memory_for_llm,
                    tools=tool_specs,
                    rag_context=rag_context,
                )
            except Exception as e:
                can_fallback = (
                    self.fallback_llm is not None
                    and "rate limit" in str(e).lower()
                )
                if can_fallback:
                    self.memory.add_event(
                        session_id,
                        "agent",
                        f"Primary LLM failed ({e}); falling back to local stub.",
                    )
                    steps.append({"type": "llm_fallback", "error": str(e)})
                    llm_resp = self.fallback_llm.decide(
                        user_goal=user_goal,
                        memory_events=memory_for_llm,
                        tools=tool_specs,
                        rag_context=rag_context,
                    )
                else:
                    msg = f"LLM decision failed: {e}"
                    self.memory.add_event(session_id, "agent", msg)
                    steps.append({"type": "llm_error", "error": str(e)})
                    return AgentResult(session_id=session_id, final_text=msg, steps=steps)
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

            if tool_name in {"search_flights_amadeus", "search_flights_priceline"}:
                validation_error = self._validate_flight_search_args(args)
                if validation_error:
                    msg = f"Blocked {tool_name}: {validation_error}"
                    self.memory.add_event(session_id, "agent", msg, meta={"requested_args": args})
                    steps.append({"type": "blocked", "tool": tool_name, "reason": msg})
                    return AgentResult(session_id=session_id, final_text=msg, steps=steps)

            # Rate limiting
            if tool.rate_limit:
                decision = self.rate_limiter.allow(session_id, tool_name, tool.rate_limit)
                if not decision.allowed:
                    msg = (
                        f"Rate limit exceeded for tool={tool_name}. "
                        f"Retry in ~{decision.retry_after_seconds}s or use a new session_id."
                    )
                    self.memory.add_event(session_id, "agent", msg)
                    steps.append(
                        {
                            "type": "rate_limited",
                            "tool": tool_name,
                            "retry_after_seconds": decision.retry_after_seconds,
                        }
                    )
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

    fallback_llm = None
    if os.environ.get("GROQ_API_KEY"):
        llm = GroqLLM()
        fallback_llm = LLMStub()
    else:
        llm = LLMStub()

    tools = build_tools()
    limiter = InMemoryRateLimiter()
    return Agent(
        memory=memory,
        llm=llm,
        tools=tools,
        rate_limiter=limiter,
        fallback_llm=fallback_llm,
    )
