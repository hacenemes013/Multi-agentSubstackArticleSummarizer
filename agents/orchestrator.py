"""Orchestrator: wires the agents together and runs articles concurrently."""
from __future__ import annotations
import logging
from concurrent.futures import ThreadPoolExecutor

from .base import log
from .critic import CriticAgent
from .discovery import ScoutAgent
from .fetcher import FetchError, ReaderAgent
from .models import ArticleResult
from .publisher import PublisherAgent
from .summarizer import SummarizerAgent


class Orchestrator:
    """
    Pipeline:  Scout -> (Reader -> Summarizer <-> Critic) per article, in parallel -> Publisher
    """

    def __init__(self, llm, length="standard", use_critic=True, max_revisions=2,
                 workers=3, limit=5, title="Substack Digest"):
        self.scout = ScoutAgent(limit=limit)
        self.reader = ReaderAgent()
        self.summarizer = SummarizerAgent(llm, length)
        self.critic = CriticAgent(llm) if use_critic else None
        self.publisher = PublisherAgent(title)
        self.max_revisions = max_revisions
        self.workers = workers

    def process_one(self, url: str) -> ArticleResult:
        res = ArticleResult(url=url)
        try:
            res.article = self.reader.run(url)
            res.summary = self.summarizer.run(res.article)
            if not self.critic:
                res.review_verdict = "skipped"
                return res
            for _ in range(self.max_revisions + 1):
                review = self.critic.run(res.article, res.summary)
                res.review_verdict = review["verdict"]
                if review["verdict"] == "pass" or res.review_rounds >= self.max_revisions:
                    break
                res.summary = self.summarizer.revise(res.article, res.summary, review["issues"])
                res.review_rounds += 1
        except FetchError as e:
            res.error = str(e)
            log.warning("[Orchestrator] %s skipped: %s", url, e)
        except Exception as e:
            res.error = f"{type(e).__name__}: {e}"
            log.error("[Orchestrator] %s failed: %s", url, res.error)
        return res

    def run(self, inputs: list[str], out_path: str, split: bool = False) -> list[ArticleResult]:
        urls = self.scout.run(inputs)
        if not urls:
            raise SystemExit("No articles found to process.")
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            results = list(pool.map(self.process_one, urls))
        self.publisher.run(results, out_path)
        if split:
            base = out_path[:-4] if out_path.lower().endswith(".pdf") else out_path
            for i, r in enumerate(x for x in results if x.ok):
                self.publisher.run([r], f"{base}_{i + 1:02d}.pdf")
        return results
