#!/usr/bin/env python3
"""Substack Digest — multi-agent pipeline: Scout → Reader → Summarizer ⇄ Critic → Publisher (PDF)."""
import argparse
import logging
import sys

from agents.base import LLM
from agents.orchestrator import Orchestrator


def main():
    ap = argparse.ArgumentParser(description="Summarize public Substack articles into a PDF digest.")
    ap.add_argument("urls", nargs="*", help="Article URLs (…/p/slug) or publication URLs (name.substack.com)")
    ap.add_argument("-f", "--urls-file", help="Text file with one URL per line")
    ap.add_argument("-n", "--limit", type=int, default=5, help="Posts to take per publication URL (default 5)")
    ap.add_argument("-o", "--out", default="output/digest.pdf", help="Output PDF path")
    ap.add_argument("--length", choices=["short", "standard", "detailed"], default="standard")
    ap.add_argument("--split", action="store_true", help="Also write one PDF per article")
    ap.add_argument("--no-critic", action="store_true", help="Skip the fact-checking agent (faster, cheaper)")
    ap.add_argument("--workers", type=int, default=3, help="Articles processed in parallel")
    ap.add_argument("--title", default="Substack Digest")
    ap.add_argument("--model", help="Claude model name (default: $CLAUDE_MODEL or claude-sonnet-5-5)")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()

    logging.basicConfig(level=logging.INFO if a.verbose else logging.WARNING,
                        format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    if a.verbose is False:
        logging.getLogger("digest").setLevel(logging.INFO)  # always show agent activity

    inputs = list(a.urls)
    if a.urls_file:
        inputs += open(a.urls_file, encoding="utf-8").read().splitlines()
    if not inputs:
        ap.error("give at least one URL or --urls-file")

    orch = Orchestrator(LLM(a.model), length=a.length, use_critic=not a.no_critic,
                        workers=a.workers, limit=a.limit, title=a.title)
    results = orch.run(inputs, a.out, split=a.split)
    ok = sum(r.ok for r in results)
    print(f"\nDone: {ok}/{len(results)} articles summarized → {a.out}")
    for r in results:
        if not r.ok:
            print(f"  skipped: {r.url} — {r.error}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
