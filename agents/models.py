"""Shared data structures passed between agents."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Article:
    url: str
    title: str = ""
    subtitle: str = ""
    author: str = ""
    publication: str = ""
    date: str = ""
    text: str = ""
    paywalled: bool = False

    @property
    def word_count(self) -> int:
        return len(self.text.split())


@dataclass
class Summary:
    headline: str = ""
    tldr: str = ""
    key_points: list = field(default_factory=list)
    takeaways: list = field(default_factory=list)
    topics: list = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "Summary":
        def lst(k):
            return [str(x).strip() for x in d.get(k, []) if str(x).strip()]
        return cls(
            headline=str(d.get("headline", "")).strip(),
            tldr=str(d.get("tldr", "")).strip(),
            key_points=lst("key_points"),
            takeaways=lst("takeaways"),
            topics=lst("topics"),
        )

    def to_dict(self) -> dict:
        return {
            "headline": self.headline, "tldr": self.tldr,
            "key_points": self.key_points, "takeaways": self.takeaways,
            "topics": self.topics,
        }


@dataclass
class ArticleResult:
    url: str
    article: Optional[Article] = None
    summary: Optional[Summary] = None
    review_rounds: int = 0
    review_verdict: str = ""          # "pass" | "revise" | "skipped"
    error: str = ""                   # set when the article could not be processed

    @property
    def ok(self) -> bool:
        return self.summary is not None and not self.error
