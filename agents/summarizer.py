"""Agent 3 — Summarizer: turns an article into a structured summary (map-reduce for long posts)."""
from __future__ import annotations
import json

from .base import Agent
from .models import Article, Summary

LENGTHS = {
    "short":    "tldr of 2 sentences; 3-4 key_points; 2 takeaways",
    "standard": "tldr of 2-3 sentences; 5-7 key_points; 3 takeaways",
    "detailed": "tldr of 3-4 sentences; 8-12 key_points; 4-5 takeaways",
}

SYSTEM = """You are a precise editorial summarizer.
Rules:
- Use ONLY information stated in the article. Never add outside facts or opinions.
- Paraphrase. Do not copy sentences; any quoted phrase must be under 15 words.
- Keep the author's claims attributed to the author ("The author argues...") when they are opinions.
- Write the summary in the SAME LANGUAGE as the article.
- Reply with a single JSON object and nothing else."""

SCHEMA = """{
  "headline": "one-line plain description of what the article is about",
  "tldr": "...",
  "key_points": ["..."],
  "takeaways": ["what a reader should remember or do"],
  "topics": ["2-4 short topic tags"]
}"""

CHUNK_CHARS = 12000
SINGLE_PASS_LIMIT = 24000


def chunk_text(text: str, size: int = CHUNK_CHARS) -> list[str]:
    chunks, cur = [], ""
    for para in text.split("\n\n"):
        if cur and len(cur) + len(para) > size:
            chunks.append(cur)
            cur = ""
        cur += para + "\n\n"
    if cur.strip():
        chunks.append(cur)
    return chunks


def _header(a: Article) -> str:
    return f"Title: {a.title}\nSubtitle: {a.subtitle}\nAuthor: {a.author}\nPublication: {a.publication}\n"


class SummarizerAgent(Agent):
    name = "Summarizer"

    def __init__(self, llm, length: str = "standard"):
        super().__init__(llm)
        self.spec = LENGTHS.get(length, LENGTHS["standard"])

    def run(self, article: Article) -> Summary:
        text = article.text
        if len(text) > SINGLE_PASS_LIMIT:
            self.say(f"Long article ({len(text)} chars): map-reduce over chunks")
            text = self._condense(article)
        prompt = (f"{_header(article)}\nARTICLE:\n{text}\n\n"
                  f"Produce the summary as JSON with this schema:\n{SCHEMA}\n"
                  f"Length: {self.spec}.")
        return Summary.from_dict(self.llm.complete_json(SYSTEM, prompt))

    def _condense(self, article: Article) -> str:
        notes = []
        parts = chunk_text(article.text)
        for i, part in enumerate(parts, 1):
            self.say(f"  notes for chunk {i}/{len(parts)}")
            notes.append(self.llm.complete(
                "You extract faithful study notes. Use only the given text. Bullet list, no preamble.",
                f"Section {i} of {len(parts)} of the article “{article.title}”:\n\n{part}\n\n"
                "List every key claim, argument, number, and conclusion as terse bullets.",
                max_tokens=1500))
        return "NOTES FROM FULL ARTICLE (in order):\n\n" + "\n\n".join(notes)

    def revise(self, article: Article, summary: Summary, issues: list[str]) -> Summary:
        self.say(f"Revising summary ({len(issues)} issue(s) from Critic)")
        text = article.text if len(article.text) <= SINGLE_PASS_LIMIT else self._condense(article)
        prompt = (f"{_header(article)}\nARTICLE:\n{text}\n\n"
                  f"CURRENT SUMMARY:\n{json.dumps(summary.to_dict(), ensure_ascii=False, indent=2)}\n\n"
                  "A fact-checker found these problems:\n- " + "\n- ".join(issues) +
                  f"\n\nFix them and return the corrected summary as JSON with this schema:\n{SCHEMA}\n"
                  f"Length: {self.spec}.")
        return Summary.from_dict(self.llm.complete_json(SYSTEM, prompt))
