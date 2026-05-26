"""Shared agentic loop runner used by all agents."""
from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

import anthropic

from .tools import TOOL_SCHEMAS, ToolContext, execute_tool

logger = logging.getLogger(__name__)

_RATE_LIMIT_WAITS = [15, 30, 60, 120]  # seconds to wait on successive 429s


@dataclass
class AgentResult:
    name: str
    text: str
    parsed: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


async def run_agent(
    client: anthropic.AsyncAnthropic,
    model: str,
    agent_name: str,
    system_prompt: str,
    initial_message: str,
    tool_context: ToolContext,
    max_turns: int = 12,
) -> AgentResult:
    messages: list[dict] = [{"role": "user", "content": initial_message}]

    for turn in range(max_turns):
        response = None
        for attempt, wait in enumerate([0] + _RATE_LIMIT_WAITS):
            if wait:
                logger.warning(
                    "Agent %s rate-limited on turn %d, waiting %ds (attempt %d)",
                    agent_name, turn, wait, attempt,
                )
                await asyncio.sleep(wait)
            try:
                response = await client.messages.create(
                    model=model,
                    max_tokens=8192,
                    system=[
                        {
                            "type": "text",
                            "text": system_prompt,
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                    tools=TOOL_SCHEMAS,
                    messages=messages,
                )
                break
            except anthropic.RateLimitError as exc:
                if attempt == len(_RATE_LIMIT_WAITS):
                    logger.error("Agent %s exhausted retries on turn %d", agent_name, turn)
                    return AgentResult(name=agent_name, text="", error=str(exc))
            except Exception as exc:
                logger.error("Agent %s failed on turn %d: %s", agent_name, turn, exc)
                return AgentResult(name=agent_name, text="", error=str(exc))
        if response is None:
            return AgentResult(name=agent_name, text="", error="rate_limit_exhausted")

        messages.append({"role": "assistant", "content": response.content})

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
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": content,
                        }
                    )
            messages.append({"role": "user", "content": tool_results})

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
