"""Agent 4 — Critic: fact-checks the summary against the source article."""
from __future__ import annotations
import json

from .base import Agent
from .models import Article, Summary

SYSTEM = """You are a strict fact-checker for article summaries.
Compare the SUMMARY to the ARTICLE and look for:
1. claims in the summary that the article does not support (hallucinations),
2. opinions presented as facts, or attributions that are wrong,
3. important points of the article that are missing or distorted,
4. numbers, names or dates that differ from the article.
Reply with ONE JSON object only:
{"verdict": "pass" | "revise", "issues": ["short, specific problem", ...]}
Use "pass" only if there are no real problems. Do not nitpick style."""

MAX_SOURCE_CHARS = 40000


class CriticAgent(Agent):
    name = "Critic"

    def run(self, article: Article, summary: Summary) -> dict:
        src = article.text
        if len(src) > MAX_SOURCE_CHARS:  # keep head + tail for very long posts
            src = src[: MAX_SOURCE_CHARS // 2] + "\n[...]\n" + src[-MAX_SOURCE_CHARS // 2:]
        prompt = (f"ARTICLE (“{article.title}”):\n{src}\n\n"
                  f"SUMMARY:\n{json.dumps(summary.to_dict(), ensure_ascii=False, indent=2)}")
        out = self.llm.complete_json(SYSTEM, prompt, max_tokens=800)
        verdict = "pass" if str(out.get("verdict", "")).lower() == "pass" else "revise"
        issues = [str(i) for i in out.get("issues", []) if str(i).strip()]
        if verdict == "revise" and not issues:
            verdict = "pass"
        self.say(f"Verdict: {verdict}" + (f" ({len(issues)} issues)" if issues else ""))
        return {"verdict": verdict, "issues": issues}
