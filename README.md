# Substack Digest — multi-agent summarizer

Give it public Substack article links (or a publication link) and it produces a PDF digest.

```
 URLs ─► Scout ─► Reader ─► Summarizer ⇄ Critic ─► Publisher ─► digest.pdf
                  (articles run in parallel)
```

| Agent | Job |
|---|---|
| **Scout** (`agents/discovery.py`) | Turns article links / a publication link into a de-duplicated list of *public* post URLs (Substack archive API, RSS fallback). |
| **Reader** (`agents/fetcher.py`) | Downloads each post (Substack JSON API, HTML fallback), strips widgets, converts to clean text. Skips paywalled posts. |
| **Summarizer** (`agents/summarizer.py`) | Claude writes a structured summary (headline, TL;DR, key points, takeaways, topics). Long posts use map-reduce over chunks. Replies in the article's language. |
| **Critic** (`agents/critic.py`) | Claude fact-checks the summary against the source; if it finds problems, the Summarizer revises (max 2 rounds). |
| **Publisher** (`agents/publisher.py`) | ReportLab lays out a cover page + one page per article. Unicode and Arabic (RTL) supported. |
| **Orchestrator** (`agents/orchestrator.py`) | Wires everything together and runs articles concurrently. |

## Setup
```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...        # required
export CLAUDE_MODEL=claude-sonnet-5-5      # optional
```

## Usage
```bash
# specific articles
python main.py https://example.substack.com/p/some-post https://other.substack.com/p/another

# latest 5 public posts of a publication
python main.py https://example.substack.com -n 5

# from a file, detailed summaries, plus one PDF per article
python main.py -f urls.txt --length detailed --split -o output/my_digest.pdf

# faster / cheaper: skip the fact-checking agent
python main.py URL --no-critic
```
Options: `--length short|standard|detailed`, `--workers N`, `--title "..."`, `--model ...`, `-v`.

## Tests (no network or API key needed)
```bash
python -m unittest discover -s tests -v
```
They use a fake Substack and a fake LLM, and write `output/sample_digest.pdf`.

## Notes
- Only **public** posts are processed; paid posts are skipped and listed on the cover page.
- Summaries are paraphrased, not copies. Respect each author's terms and keep digests for personal use.
- Custom-domain Substacks work too, as long as the URL contains `/p/<slug>`.
