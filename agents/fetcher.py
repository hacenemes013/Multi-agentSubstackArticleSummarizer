"""Agent 2 — Reader: downloads a public Substack post and cleans it into plain text."""
from __future__ import annotations
import copy
import re
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from .base import Agent
from .models import Article

UA = {"User-Agent": "Mozilla/5.0 (compatible; SubstackDigestBot/1.0)"}
NOISE = ("subscription-widget", "button-wrapper", "captioned-button", "share-dialog",
         "footnote-hover", "paywall", "subscribe-widget", "post-ufi")


class FetchError(RuntimeError):
    pass


def html_to_text(html: str) -> str:
    """Convert Substack body HTML to readable text with '## ' headings and '- ' bullets."""
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "figure", "svg", "button", "iframe", "form", "img"]):
        tag.decompose()
    for el in soup.find_all(class_=lambda c: c and any(n in c for n in NOISE)):
        try:
            el.decompose()
        except Exception:
            pass
    blocks: list[str] = []
    for el in soup.find_all(["h1", "h2", "h3", "h4", "p", "li", "blockquote"]):
        if el.name == "blockquote" and el.find("p"):
            continue  # inner <p> handled separately
        if el.name == "p" and el.find_parent("li"):
            continue  # <li> text already includes it
        node = el
        if el.name == "li":
            node = copy.copy(el)
            for sub in node.find_all(["ul", "ol"]):
                sub.decompose()
        txt = re.sub(r"\s+", " ", node.get_text()).strip()
        if not txt:
            continue
        if el.name in ("h1", "h2", "h3", "h4"):
            blocks.append(f"## {txt}")
        elif el.name == "li":
            blocks.append(f"- {txt}")
        elif el.name == "blockquote" or el.find_parent("blockquote"):
            blocks.append(f"> {txt}")
        else:
            blocks.append(txt)
    return "\n\n".join(blocks)


class ReaderAgent(Agent):
    name = "Reader"

    def __init__(self, timeout: int = 25, min_words: int = 40):
        super().__init__(None)
        self.timeout = timeout
        self.min_words = min_words

    def run(self, url: str) -> Article:
        p = urlparse(url)
        m = re.match(r"^/p/([^/?#]+)", p.path)
        art = None
        if m:
            art = self._via_api(f"{p.scheme}://{p.netloc}", m.group(1), url)
        if art is None:
            art = self._via_html(url)
        if art.paywalled:
            raise FetchError("post is paywalled (not public) — skipped")
        if art.word_count < self.min_words:
            raise FetchError(f"extracted text too short ({art.word_count} words)")
        self.say(f"Fetched “{art.title}” ({art.word_count} words)")
        return art

    # --- strategy 1: Substack JSON API (clean, structured) ---
    def _via_api(self, base: str, slug: str, url: str) -> Article | None:
        try:
            r = requests.get(f"{base}/api/v1/posts/{slug}", headers=UA, timeout=self.timeout)
            if r.status_code != 200:
                return None
            d = r.json()
            body = d.get("body_html") or ""
            bylines = d.get("publishedBylines") or []
            pub = (d.get("publication") or {}).get("name") or urlparse(base).netloc
            return Article(
                url=d.get("canonical_url") or url,
                title=d.get("title", ""),
                subtitle=d.get("subtitle") or d.get("description") or "",
                author=", ".join(b.get("name", "") for b in bylines if b.get("name")),
                publication=pub,
                date=(d.get("post_date") or "")[:10],
                text=html_to_text(body),
                paywalled=d.get("audience", "everyone") != "everyone",
            )
        except Exception as e:
            self.say(f"API route failed ({e}); falling back to HTML")
            return None

    # --- strategy 2: scrape the public HTML page ---
    def _via_html(self, url: str) -> Article:
        try:
            r = requests.get(url, headers=UA, timeout=self.timeout)
            r.raise_for_status()
        except Exception as e:
            raise FetchError(f"download failed: {e}") from e
        soup = BeautifulSoup(r.text, "html.parser")
        og = lambda k: (soup.find("meta", property=k) or {}).get("content", "")
        body = (soup.select_one("div.available-content") or soup.select_one("div.body.markup")
                or soup.select_one("article"))
        paywalled = bool(soup.select_one("div.paywall")) or "This post is for paid subscribers" in r.text
        return Article(
            url=url,
            title=og("og:title") or (soup.title.string if soup.title else ""),
            subtitle=og("og:description"),
            author=(soup.find("meta", attrs={"name": "author"}) or {}).get("content", ""),
            publication=og("og:site_name") or urlparse(url).netloc,
            date=(og("article:published_time") or "")[:10],
            text=html_to_text(str(body)) if body else "",
            paywalled=paywalled,
        )
