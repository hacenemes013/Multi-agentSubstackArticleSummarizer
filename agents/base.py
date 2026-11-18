"""Base agent + thin Claude client wrapper."""
from __future__ import annotations
import json
import logging
import os
import re
import time

log = logging.getLogger("digest")

DEFAULT_MODEL = "claude-sonnet-5-5"


class LLMError(RuntimeError):
    pass


class LLM:
    """Minimal wrapper around the Anthropic Messages API with retries."""

    def __init__(self, model: str | None = None, max_tokens: int = 2500, retries: int = 3):
        import anthropic  # imported lazily so tests can run without it
        self.client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
        self.model = model or os.getenv("CLAUDE_MODEL", DEFAULT_MODEL)
        self.max_tokens = max_tokens
        self.retries = retries

    def complete(self, system: str, user: str, max_tokens: int | None = None) -> str:
        last = None
        for attempt in range(1, self.retries + 1):
            try:
                resp = self.client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens or self.max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                )
                return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
            except Exception as e:  # network, rate limit, overloaded...
                last = e
                time.sleep(2 ** attempt)
        raise LLMError(f"LLM call failed after {self.retries} attempts: {last}")

    def complete_json(self, system: str, user: str, max_tokens: int | None = None) -> dict:
        return parse_json(self.complete(system, user, max_tokens))


def parse_json(text: str) -> dict:
    """Extract a JSON object from a model reply (tolerates code fences / chatter)."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise LLMError(f"No JSON object in model reply: {text[:200]!r}")
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError as e:
        raise LLMError(f"Invalid JSON from model: {e}") from e


class Agent:
    """Every agent has a name, one responsibility, and (optionally) an LLM."""
    name = "agent"

    def __init__(self, llm: LLM | None = None):
        self.llm = llm

    def say(self, msg: str):
        log.info("[%s] %s", self.name, msg)
