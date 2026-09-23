"""The Yale SOM course agent.

Two tools only:
  * ``search_courses``  — a Python function over the ``courses`` table
  * ``web_search``      — OpenAI's *native* web search, wired as a provider capability

Every run is appended to ``output/audit_trail.json`` at the project root.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from models import AgentResult, AuditEntry, ToolCallRecord
from tools import search_courses

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PROMPT_PATH = HERE / "prompts" / "prompt.md"
AUDIT_PATH = ROOT / "output" / "audit_trail.json"

# The key may sit next to the lecture or one level up in the course folder.
load_dotenv(ROOT / ".env")
load_dotenv(ROOT.parent / ".env")

MODEL_NAME = os.getenv("COURSE_AGENT_MODEL", "gpt-5.6-sol")
PORTKEY_BASE_URL = os.getenv("PORTKEY_BASE_URL", "https://api.portkey.ai/v1")

_audit_lock = threading.Lock()
_agent_lock = threading.Lock()
_agent = None


def _instructions() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def build_agent():
    """Construct the pydantic-ai agent. Cached — the first call does the work."""
    global _agent
    with _agent_lock:
        if _agent is not None:
            return _agent

        from openai import AsyncOpenAI
        from pydantic_ai import Agent
        from pydantic_ai.capabilities import NativeTool
        from pydantic_ai.models.openai import OpenAIResponsesModel
        from pydantic_ai.native_tools import WebSearchTool
        from pydantic_ai.providers.openai import OpenAIProvider

        api_key = os.getenv("PORTKEY_API_KEY")
        if not api_key:
            raise RuntimeError(
                "PORTKEY_API_KEY is not set. Put it in Lecture 7/.env or MGT409/.env "
                "(see .env.example)."
            )

        client = AsyncOpenAI(
            api_key=api_key,
            base_url=PORTKEY_BASE_URL,
            default_headers={"x-portkey-provider": "openai"},
        )
        # The Responses API is what exposes OpenAI's native web_search tool.
        model = OpenAIResponsesModel(
            MODEL_NAME, provider=OpenAIProvider(openai_client=client)
        )

        _agent = Agent(
            model,
            instructions=_instructions(),
            tools=[search_courses],
            capabilities=[NativeTool(WebSearchTool())],
        )
        return _agent


def _preview(value: Any, limit: int = 400) -> str:
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            text = str(value)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _as_dict(args: Any) -> dict[str, Any]:
    if isinstance(args, dict):
        return args
    if isinstance(args, str):
        try:
            parsed = json.loads(args)
            return parsed if isinstance(parsed, dict) else {"_raw": args}
        except json.JSONDecodeError:
            return {"_raw": args}
    return {} if args is None else {"_raw": str(args)}


def _dissect(messages: list[Any]) -> tuple[list[str], list[ToolCallRecord], list[str]]:
    """Pull thoughts, tool calls and tool names out of the run's message history."""
    from pydantic_ai.messages import (
        NativeToolCallPart,
        NativeToolReturnPart,
        TextPart,
        ThinkingPart,
        ToolCallPart,
        ToolReturnPart,
    )

    thoughts: list[str] = []
    calls: list[ToolCallRecord] = []
    tools_used: list[str] = []
    returns: dict[str, Any] = {}

    parts = [p for m in messages for p in getattr(m, "parts", [])]

    # First pass: collect results so each call can carry its own preview.
    for part in parts:
        if isinstance(part, (ToolReturnPart, NativeToolReturnPart)):
            key = getattr(part, "tool_call_id", None)
            if key:
                returns[key] = getattr(part, "content", None)

    for part in parts:
        if isinstance(part, ThinkingPart):
            text = (getattr(part, "content", "") or "").strip()
            if text:
                thoughts.append(text)
        elif isinstance(part, NativeToolCallPart):
            name = part.tool_name
            if name not in tools_used:
                tools_used.append(name)
            calls.append(
                ToolCallRecord(
                    tool=name,
                    kind="native",
                    args=_as_dict(part.args),
                    result_preview=_preview(returns.get(part.tool_call_id, "")),
                )
            )
        elif isinstance(part, ToolCallPart):
            name = part.tool_name
            if name not in tools_used:
                tools_used.append(name)
            calls.append(
                ToolCallRecord(
                    tool=name,
                    kind="function",
                    args=_as_dict(part.args),
                    result_preview=_preview(returns.get(part.tool_call_id, "")),
                )
            )
        elif isinstance(part, TextPart):
            # Intermediate narration (not the final answer) reads as a thought.
            text = (getattr(part, "content", "") or "").strip()
            if text and part is not parts[-1]:
                thoughts.append(text)

    return thoughts, calls, tools_used


def append_audit(entry: AuditEntry) -> None:
    """Append one row to output/audit_trail.json, never dropping earlier rows."""
    with _audit_lock:
        AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)

        rows: list[dict[str, Any]] = []
        if AUDIT_PATH.exists():
            raw = AUDIT_PATH.read_text(encoding="utf-8").strip()
            if raw:
                try:
                    loaded = json.loads(raw)
                    rows = loaded if isinstance(loaded, list) else [loaded]
                except json.JSONDecodeError:
                    # Move the unreadable file aside rather than overwrite history.
                    AUDIT_PATH.replace(AUDIT_PATH.with_suffix(".corrupt.json"))
                    rows = []

        rows.append(entry.model_dump())
        AUDIT_PATH.write_text(
            json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _to_history(history: list[dict[str, str]] | None) -> list[Any]:
    """Turn stored chat rows into pydantic-ai messages the model can read.

    Only the text is replayed, not the original tool calls — a recorded call would
    need its matching return part to stay valid, and the reply already summarises
    whatever the tool found.
    """
    if not history:
        return []

    from pydantic_ai.messages import (
        ModelRequest,
        ModelResponse,
        TextPart,
        UserPromptPart,
    )

    messages: list[Any] = []
    for turn in history:
        content = (turn.get("content") or "").strip()
        if not content:
            continue
        if turn.get("role") == "user":
            messages.append(ModelRequest(parts=[UserPromptPart(content=content)]))
        else:
            messages.append(ModelResponse(parts=[TextPart(content=content)]))
    return messages


def run_agent(message: str, history: list[dict[str, str]] | None = None) -> dict:
    """Answer one user message. Returns ``{"reply": str, "tools_used": list[str]}``.

    ``history`` is this user's earlier turns, oldest first, so follow-ups like
    "what about on Fridays?" resolve against what was already asked.
    """
    started = _now()

    try:
        agent = build_agent()
        result = _run_sync(agent, message, _to_history(history))
    except Exception as exc:  # surface the problem instead of a blank chat bubble
        reply = f"The agent hit an error: {type(exc).__name__}: {exc}"
        append_audit(
            AuditEntry(
                time=started,
                model=MODEL_NAME,
                user_message=message,
                reply=reply,
                stop_reason=f"error:{type(exc).__name__}",
            )
        )
        return AgentResult(reply=reply, tools_used=[]).model_dump()

    messages = result.all_messages()
    thoughts, calls, tools_used = _dissect(messages)
    reply = result.output if isinstance(result.output, str) else str(result.output)

    usage = getattr(result, "usage", None)
    usage_dict: dict[str, Any] = {}
    if usage is not None:
        for field in ("requests", "input_tokens", "output_tokens"):
            value = getattr(usage, field, None)
            if value is not None:
                usage_dict[field] = value

    append_audit(
        AuditEntry(
            time=started,
            model=MODEL_NAME,
            user_message=message,
            thoughts=thoughts,
            tool_calls=calls,
            reply=reply,
            tools_used=tools_used,
            stop_reason="final_reply" if reply else "empty_reply",
            usage=usage_dict,
        )
    )

    return AgentResult(reply=reply, tools_used=tools_used).model_dump()


def _run_sync(agent, message: str, message_history: list[Any] | None = None):
    """Run the agent from sync code, whether or not a loop is already running."""
    history = message_history or None
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return agent.run_sync(message, message_history=history)

    # Called from inside an event loop — hand the coroutine to a worker thread.
    box: dict[str, Any] = {}

    def worker() -> None:
        try:
            box["value"] = asyncio.run(agent.run(message, message_history=history))
        except BaseException as exc:  # noqa: BLE001 - re-raised on the caller's thread
            box["error"] = exc

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    thread.join()
    if "error" in box:
        raise box["error"]
    return box["value"]


if __name__ == "__main__":
    import sys

    question = " ".join(sys.argv[1:]) or "What finance courses meet on Tuesdays?"
    out = run_agent(question)
    print(out["reply"])
    print("\ntools_used:", out["tools_used"])
