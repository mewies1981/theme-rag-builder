"""
Anime Setup Orchestrator — agentic loop using GPT-4o + tool use.

Usage (from theme-rag-builder/):
    PYTHONPATH=. venv/bin/python3 orchestrator/orchestrator_agent.py \\
        "Set up Attack on Titan completely"

    PYTHONPATH=. venv/bin/python3 orchestrator/orchestrator_agent.py \\
        "Add 20 more characters to One Piece"

    PYTHONPATH=. venv/bin/python3 orchestrator/orchestrator_agent.py \\
        "Check the status of all supported anime"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterator

from dotenv import load_dotenv
from openai import OpenAI

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

load_dotenv(_PROJECT_ROOT / ".env")

from orchestrator.tool_definitions import SYSTEM_PROMPT, TOOLS
from orchestrator.tool_executor import execute_tool

MODEL     = "gpt-4o"
MAX_TURNS = 20


# ── Core loop ─────────────────────────────────────────────────────────────────

def run(instruction: str) -> Iterator[str]:
    """
    Run the orchestrator for a given instruction.
    Yields human-readable progress lines as the agent works.
    """
    client   = OpenAI()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": instruction},
    ]

    for _ in range(MAX_TURNS):
        response = client.chat.completions.create(
            model    = MODEL,
            messages = messages,
            tools    = TOOLS,
        )

        choice  = response.choices[0]
        message = choice.message

        # Emit any text the model produced
        if message.content:
            yield message.content

        # Done?
        if choice.finish_reason == "stop":
            break

        # Execute tool calls
        if choice.finish_reason == "tool_calls":
            messages.append(message)  # append assistant turn with tool_calls

            for tc in message.tool_calls:
                name  = tc.function.name
                inp   = json.loads(tc.function.arguments)

                yield f"\n⚙  {name}({_summarise_input(inp)})\n"
                result = execute_tool(name, inp)
                yield f"   → {_summarise_result(result)}\n"

                messages.append({
                    "role":         "tool",
                    "tool_call_id": tc.id,
                    "content":      json.dumps(result),
                })
        else:
            yield f"\n[unexpected finish_reason: {choice.finish_reason}]\n"
            break

    else:
        yield f"\n[hit MAX_TURNS={MAX_TURNS} — stopping]\n"


# ── Formatting helpers ────────────────────────────────────────────────────────

def _summarise_input(inp: dict) -> str:
    parts   = [f"{k}={json.dumps(v)}" for k, v in inp.items()]
    summary = ", ".join(parts)
    return summary[:120] + "…" if len(summary) > 120 else summary


def _summarise_result(result: dict) -> str:
    if not result.get("success"):
        return f"ERROR: {result.get('error', 'unknown')}"
    parts   = [f"{k}={v}" for k, v in result.items() if k not in ("success", "anime")]
    summary = "  ".join(parts)
    return summary[:200] + "…" if len(summary) > 200 else summary


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Anime Setup Orchestrator — natural-language database management"
    )
    parser.add_argument(
        "instruction",
        nargs="?",
        default="Check the status of all supported anime and tell me which ones need more characters.",
        help='Natural-language task, e.g. "Set up Demon Slayer completely"',
    )
    args = parser.parse_args()

    print(f"\n🤖  Orchestrator  [{MODEL}]\n{'─' * 60}")
    for chunk in run(args.instruction):
        print(chunk, end="", flush=True)
    print(f"\n{'─' * 60}")
