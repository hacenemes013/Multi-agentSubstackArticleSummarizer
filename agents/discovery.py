"""Agent 1 — Scout: turns user input (article links or a publication link) into article URLs."""
from __future__ import annotations
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

import requests

from .base import Agent

UA = {"User-Agent": "Mozilla/5.0 (compatible; SubstackDigestBot/1.0)"}


class ScoutAgent(Agent):
    name = "Scout"

    def __init__(self, limit: int = 5, timeout: int = 20):
        super().__init__(None)
        self.limit = limit
        self.timeout = timeout

    def run(self, inputs: list[str]) -> list[str]:
        urls: list[str] = []
        for raw in inputs:
            raw = raw.strip()
            if not raw or raw.startswith("#"):
                continue
            if not raw.startswith("http"):
                raw = "https://" + raw
            path = urlparse(raw).path
            if "/p/" in path:
                urls.append(raw)
            else:
                self.say(f"Publication detected: {raw} — looking for the latest {self.limit} public posts")
                urls.extend(self._latest_posts(raw))
        seen, unique = set(), []
        for u in urls:
            key = u.split("?")[0].rstrip("/")
            if key not in seen:
                seen.add(key)
                unique.append(u)
        self.say(f"{len(unique)} article(s) queued")
        return unique

    def _latest_posts(self, pub_url: str) -> list[str]:
        p = urlparse(pub_url)
        base = f"{p.scheme}://{p.netloc}"
        try:
            r = requests.get(f"{base}/api/v1/archive",
                             params={"sort": "new", "limit": self.limit * 3},
                             headers=UA, timeout=self.timeout)
            r.raise_for_status()
            posts = [x for x in r.json() if x.get("audience", "everyone") == "everyone"
                     and x.get("canonical_url")]
            urls = [x["canonical_url"] for x in posts][: self.limit]
            if urls:
                return urls
        except Exception as e:
            self.say(f"Archive API failed ({e}); trying RSS feed")
        try:
            r = requests.get(f"{base}/feed", headers=UA, timeout=self.timeout)
            r.raise_for_status()
            root = ET.fromstring(r.content)
            return [i.findtext("link") for i in root.iter("item") if i.findtext("link")][: self.limit]
        except Exception as e:
            self.say(f"RSS feed failed too: {e}")
            return []
