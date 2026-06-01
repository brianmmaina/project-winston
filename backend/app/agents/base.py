"""Shared agentic loop runner — supports Anthropic and OpenAI-compatible backends (Groq etc.)."""
from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from .tools import TOOL_SCHEMAS, ToolContext, execute_tool

logger = logging.getLogger(__name__)

_RATE_LIMIT_WAITS = [15, 30, 60, 120]  # seconds to wait on successive 429s

# OpenAI-compatible tool schema (used for Groq and any OpenAI endpoint)
_OPENAI_TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": t["name"],
            "description": t.get("description", ""),
            "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
        },
    }
    for t in TOOL_SCHEMAS
]


@dataclass
class AgentResult:
    name: str
    text: str
    parsed: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


def _is_anthropic(client: Any) -> bool:
    return type(client).__name__ == "AsyncAnthropic"


async def run_agent(
    client: Any,
    model: str,
    agent_name: str,
    system_prompt: str,
    initial_message: str,
    tool_context: ToolContext,
    max_turns: int = 12,
) -> AgentResult:
    if _is_anthropic(client):
        return await _run_anthropic(client, model, agent_name, system_prompt, initial_message, tool_context, max_turns)
    return await _run_openai(client, model, agent_name, system_prompt, initial_message, tool_context, max_turns)


# ---------------------------------------------------------------------------
# Anthropic path
# ---------------------------------------------------------------------------

async def _run_anthropic(
    client: Any,
    model: str,
    agent_name: str,
    system_prompt: str,
    initial_message: str,
    tool_context: ToolContext,
    max_turns: int,
) -> AgentResult:
    import anthropic as _anthropic

    messages: list[dict] = [{"role": "user", "content": initial_message}]

    for turn in range(max_turns):
        response = None
        for attempt, wait in enumerate([0] + _RATE_LIMIT_WAITS):
            if wait:
                logger.warning("Agent %s rate-limited turn %d, waiting %ds", agent_name, turn, wait)
                await asyncio.sleep(wait)
            try:
                response = await client.messages.create(
                    model=model,
                    max_tokens=2048,
                    system=[{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
                    tools=TOOL_SCHEMAS,
                    messages=messages,
                )
                break
            except _anthropic.RateLimitError as exc:
                if attempt == len(_RATE_LIMIT_WAITS):
                    logger.error("Agent %s exhausted retries turn %d", agent_name, turn)
                    return AgentResult(name=agent_name, text="", error=str(exc))
            except Exception as exc:
                logger.error("Agent %s failed turn %d: %s", agent_name, turn, exc)
                return AgentResult(name=agent_name, text="", error=str(exc))

        if response is None:
            return AgentResult(name=agent_name, text="", error="rate_limit_exhausted")

        # Anthropic rejects messages where a TextBlock ends with trailing whitespace.
        # Convert content blocks to dicts and strip to avoid the 400 error.
        cleaned: list[dict] = []
        for blk in response.content:
            if blk.type == "text":
                cleaned.append({"type": "text", "text": blk.text.rstrip() or " "})
            elif blk.type == "tool_use":
                cleaned.append({"type": "tool_use", "id": blk.id, "name": blk.name, "input": blk.input})
            else:
                cleaned.append(blk)
        messages.append({"role": "assistant", "content": cleaned})

        if response.stop_reason == "end_turn":
            text = "".join(b.text for b in response.content if hasattr(b, "text"))
            return AgentResult(name=agent_name, text=text, parsed=_extract_json(text))

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    try:
                        result = await execute_tool(block.name, block.input, tool_context)
                        content = json.dumps(result, default=str)
                    except Exception as exc:
                        logger.warning("Tool %s raised: %s", block.name, exc)
                        content = json.dumps({"error": str(exc)})
                    tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": content})
            messages.append({"role": "user", "content": tool_results})

    logger.warning("Agent %s hit max_turns=%d", agent_name, max_turns)
    return AgentResult(name=agent_name, text="Max turns reached", error="max_turns_exceeded")


# ---------------------------------------------------------------------------
# OpenAI-compatible path (Groq, OpenAI, Ollama, etc.)
# ---------------------------------------------------------------------------

async def _run_openai(
    client: Any,
    model: str,
    agent_name: str,
    system_prompt: str,
    initial_message: str,
    tool_context: ToolContext,
    max_turns: int,
) -> AgentResult:
    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": initial_message},
    ]

    for turn in range(max_turns):
        response = None
        for attempt, wait in enumerate([0] + _RATE_LIMIT_WAITS):
            if wait:
                logger.warning("Agent %s rate-limited turn %d, waiting %ds", agent_name, turn, wait)
                await asyncio.sleep(wait)
            try:
                response = await client.chat.completions.create(
                    model=model,
                    max_tokens=2048,
                    tools=_OPENAI_TOOL_SCHEMAS,
                    messages=messages,
                )
                break
            except Exception as exc:
                err = str(exc)
                is_rate_limit = (
                    "429" in err
                    or "rate_limit" in err.lower()
                    or "RateLimitError" in type(exc).__name__
                )
                if is_rate_limit and attempt < len(_RATE_LIMIT_WAITS):
                    continue
                logger.error("Agent %s failed turn %d: %s", agent_name, turn, exc)
                return AgentResult(name=agent_name, text="", error=err)

        if response is None:
            return AgentResult(name=agent_name, text="", error="rate_limit_exhausted")

        choice = response.choices[0]
        msg = choice.message

        if choice.finish_reason in ("stop", "end_turn", None) and not msg.tool_calls:
            text = msg.content or ""
            return AgentResult(name=agent_name, text=text, parsed=_extract_json(text))

        if choice.finish_reason == "tool_calls" or msg.tool_calls:
            # Append assistant message with tool_calls
            messages.append({
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in (msg.tool_calls or [])
                ],
            })
            for tc in (msg.tool_calls or []):
                try:
                    args = json.loads(tc.function.arguments or "{}")
                    result = await execute_tool(tc.function.name, args, tool_context)
                    content = json.dumps(result, default=str)
                except Exception as exc:
                    logger.warning("Tool %s raised: %s", tc.function.name, exc)
                    content = json.dumps({"error": str(exc)})
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": content})
        else:
            # Unexpected finish reason — treat as end
            text = msg.content or ""
            return AgentResult(name=agent_name, text=text, parsed=_extract_json(text))

    logger.warning("Agent %s hit max_turns=%d", agent_name, max_turns)
    return AgentResult(name=agent_name, text="Max turns reached", error="max_turns_exceeded")


def _extract_json(text: str) -> dict[str, Any]:
    m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    stripped = text.strip()
    if stripped.startswith("{"):
        try:
            return json.loads(stripped)
        except Exception:
            pass
    return {}
