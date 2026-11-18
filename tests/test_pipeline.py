"""Offline tests: fake Substack + fake LLM, so no network or API key is needed.
Run:  python -m unittest discover -s tests -v
Also writes output/sample_digest.pdf so you can eyeball the layout.
"""
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.base import parse_json
from agents.fetcher import html_to_text
from agents.orchestrator import Orchestrator

PARA = ("Attention spans are not collapsing as fast as headlines claim, and the evidence for a steady decline "
        "is thinner than most people assume. ") * 4

BODY_EN = f"""
<div class="available-content"><div class="body markup">
<h2>The claim</h2><p>{PARA}</p>
<div class="subscription-widget-wrap"><p>Subscribe now!</p></div>
<ul><li>Studies are small<ul><li>and often unreplicated</li></ul></li><li>Measures differ</li></ul>
<blockquote><p>An inner quote</p></blockquote>
<h2>The evidence</h2><p>{PARA}</p>
</div></div>"""

BODY_AR = "<p>" + ("هذا نص عربي للاختبار حول الانتباه والتركيز في العصر الرقمي. " * 8) + "</p>"

POSTS = {
    "good": {"title": "Is your attention span really shrinking?", "subtitle": "A look at the evidence",
             "body_html": BODY_EN, "audience": "everyone", "post_date": "2026-09-01T10:00:00Z",
             "publishedBylines": [{"name": "Jane Writer"}], "canonical_url": "https://demo.substack.com/p/good"},
    "paid": {"title": "Paid post", "body_html": BODY_EN, "audience": "only_paid",
             "canonical_url": "https://demo.substack.com/p/paid"},
    "arabic": {"title": "الانتباه في العصر الرقمي", "subtitle": "قراءة في الأدلة", "body_html": BODY_AR,
               "audience": "everyone", "post_date": "2026-09-02T10:00:00Z",
               "publishedBylines": [{"name": "كاتب"}], "canonical_url": "https://demo.substack.com/p/arabic"},
}


class FakeResp:
    def __init__(self, data, status=200):
        self._d, self.status_code, self.text, self.content = data, status, "", b""

    def json(self):
        return self._d

    def raise_for_status(self):
        pass


def fake_get(url, params=None, **kw):
    if "/api/v1/archive" in url:
        return FakeResp([{"canonical_url": p["canonical_url"], "audience": p["audience"]} for p in POSTS.values()])
    slug = url.rstrip("/").split("/")[-1]
    return FakeResp(POSTS[slug]) if slug in POSTS else FakeResp({}, 404)


class FakeLLM:
    """Critic rejects the first summary of each article, then passes the revision."""
    def __init__(self):
        self.calls = []
        self.critic_seen = {}

    def complete(self, system, user, max_tokens=None):
        self.calls.append("notes")
        return "- a note"

    def complete_json(self, system, user, max_tokens=None):
        if "fact-checker for article summaries" in system:
            key = user[:60]
            n = self.critic_seen.get(key, 0)
            self.critic_seen[key] = n + 1
            self.calls.append("critic")
            return {"verdict": "revise", "issues": ["TL;DR overstates the evidence"]} if n == 0 \
                else {"verdict": "pass", "issues": []}
        revised = "A fact-checker found" in user
        self.calls.append("revise" if revised else "summarize")
        ar = "هذا نص عربي" in user
        return {
            "headline": "Attention spans and the evidence",
            "tldr": ("ملخص قصير حول الانتباه والتركيز." if ar else
                     "The author argues the 'attention crisis' is overstated: the data is thin, small and inconsistent.")
                    + (" (revised)" if revised else ""),
            "key_points": ["النقطة الأولى عن الانتباه", "النقطة الثانية"] if ar else
                          ["Studies cited are small & often unreplicated", "Measures of 'attention' differ <a lot>",
                           "Headlines outrun the evidence"],
            "takeaways": ["Be skeptical of dramatic claims"], "topics": ["attention", "media"],
        }


class Tests(unittest.TestCase):
    def test_parse_json_tolerates_fences(self):
        self.assertEqual(parse_json('Sure!\n```json\n{"a": 1}\n```'), {"a": 1})

    def test_html_cleaning(self):
        t = html_to_text(BODY_EN)
        self.assertIn("## The claim", t)
        self.assertNotIn("Subscribe now", t)
        self.assertIn("- Studies are small", t)
        self.assertIn("- and often unreplicated", t)
        self.assertIn("> An inner quote", t)

    def test_full_pipeline(self):
        llm = FakeLLM()
        out = os.path.join(os.path.dirname(__file__), "..", "output", "sample_digest.pdf")
        with mock.patch("requests.get", side_effect=fake_get):
            orch = Orchestrator(llm, workers=2, limit=5)
            results = orch.run(["https://demo.substack.com"], out, split=True)
        by_url = {r.url.split("/")[-1]: r for r in results}
        self.assertTrue(by_url["good"].ok)
        self.assertEqual(by_url["good"].review_rounds, 1)           # critic -> revise -> pass
        self.assertEqual(by_url["good"].review_verdict, "pass")
        self.assertIn("(revised)", by_url["good"].summary.tldr)
        self.assertTrue(by_url["arabic"].ok)
        self.assertNotIn("paid", by_url)                             # Scout filters paid posts out
        self.assertTrue(os.path.getsize(out) > 3000)
        with open(out, "rb") as f:
            self.assertEqual(f.read(4), b"%PDF")

    def test_paid_post_is_skipped_explicitly(self):
        with mock.patch("requests.get", side_effect=fake_get):
            orch = Orchestrator(FakeLLM())
            r = orch.process_one("https://demo.substack.com/p/paid")
        self.assertIn("paywalled", r.error)


if __name__ == "__main__":
    unittest.main()
