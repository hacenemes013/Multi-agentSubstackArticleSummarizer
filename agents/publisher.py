"""Agent 5 — Publisher: lays out the summaries as a clean PDF digest (ReportLab)."""
from __future__ import annotations
import os
import re
from datetime import date
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (HRFlowable, KeepTogether, PageBreak, Paragraph,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

from .base import Agent
from .models import ArticleResult

try:  # optional Arabic support
    import arabic_reshaper
    from bidi.algorithm import get_display
except Exception:  # pragma: no cover
    arabic_reshaper = get_display = None

ARABIC_RE = re.compile(r"[\u0600-\u06FF]")
INK, MUTED, ACCENT, PANEL = (colors.HexColor(c) for c in ("#1f2430", "#6b7280", "#2f5d8a", "#eef3f8"))

FONT_CANDIDATES = [
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"),
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
    ("/Library/Fonts/Arial Unicode.ttf", "/Library/Fonts/Arial Unicode.ttf"),
]


def _register_fonts() -> tuple[str, str]:
    for reg, bold in FONT_CANDIDATES:
        if os.path.exists(reg) and os.path.exists(bold):
            try:
                pdfmetrics.registerFont(TTFont("DigestSans", reg))
                pdfmetrics.registerFont(TTFont("DigestSans-Bold", bold))
                return "DigestSans", "DigestSans-Bold"
            except Exception:
                continue
    return "Helvetica", "Helvetica-Bold"   # no Unicode coverage, fine for Latin text


class PublisherAgent(Agent):
    name = "Publisher"

    def __init__(self, title: str = "Substack Digest"):
        super().__init__(None)
        self.title = title
        self.font, self.bold = _register_fonts()
        self._styles()

    # ---------- text helpers ----------
    def _t(self, text: str) -> tuple[str, bool]:
        """Escape for ReportLab and apply Arabic shaping/bidi when needed. Returns (text, is_rtl)."""
        rtl = bool(ARABIC_RE.search(text or ""))
        if rtl and arabic_reshaper and get_display:
            text = get_display(arabic_reshaper.reshape(text))
        return escape(text or ""), rtl

    def P(self, text, style, **kw):
        s, rtl = self._t(text)
        if rtl:
            style = ParagraphStyle(style.name + "_rtl", parent=style, alignment=TA_RIGHT)
        return Paragraph(s, style, **kw)

    def _styles(self):
        b = getSampleStyleSheet()["Normal"]
        mk = lambda n, **k: ParagraphStyle(n, parent=b, **{"fontName": self.font, **k})
        self.s = {
            "cover_title": mk("ct", fontName=self.bold, fontSize=30, leading=36, textColor=INK, spaceAfter=6),
            "cover_sub":   mk("cs", fontSize=11, leading=16, textColor=MUTED, spaceAfter=18),
            "toc":         mk("toc", fontSize=11, leading=18, textColor=INK, leftIndent=0),
            "h1":          mk("h1", fontName=self.bold, fontSize=18, leading=23, textColor=INK, spaceAfter=3),
            "sub":         mk("sub", fontSize=10.5, leading=15, textColor=MUTED, spaceAfter=3),
            "meta":        mk("meta", fontSize=8.5, leading=12, textColor=MUTED),
            "h2":          mk("h2", fontName=self.bold, fontSize=11, leading=14, textColor=ACCENT,
                              spaceBefore=12, spaceAfter=4),
            "body":        mk("body", fontSize=10, leading=15, textColor=INK),
            "bullet":      mk("bullet", fontSize=10, leading=14.5, textColor=INK, leftIndent=14,
                              bulletIndent=2, spaceAfter=3),
            "tag":         mk("tag", fontSize=8.5, leading=12, textColor=ACCENT),
            "err":         mk("err", fontSize=9.5, leading=13, textColor=colors.HexColor("#9b2c2c")),
        }

    # ---------- document ----------
    def run(self, results: list[ArticleResult], out_path: str) -> str:
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        doc = SimpleDocTemplate(out_path, pagesize=A4, title=self.title, author="Substack Digest Agents",
                                leftMargin=20 * mm, rightMargin=20 * mm, topMargin=20 * mm, bottomMargin=20 * mm)
        ok = [r for r in results if r.ok]
        failed = [r for r in results if not r.ok]
        story = self._cover(ok, failed)
        for r in ok:
            story.append(PageBreak())
            story.extend(self._article(r))
        doc.build(story, onFirstPage=self._footer, onLaterPages=self._footer)
        self.say(f"PDF written: {out_path} ({len(ok)} summaries, {len(failed)} skipped)")
        return out_path

    def _footer(self, canvas, doc):
        canvas.saveState()
        canvas.setFont(self.font, 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(20 * mm, 10 * mm, self.title)
        canvas.drawRightString(A4[0] - 20 * mm, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()

    def _cover(self, ok, failed):
        s = self.s
        out = [Spacer(1, 40 * mm), Paragraph(escape(self.title), s["cover_title"]),
               Paragraph(f"{date.today():%d %B %Y} &nbsp;·&nbsp; {len(ok)} article(s) summarized", s["cover_sub"]),
               HRFlowable(width="100%", thickness=1.2, color=ACCENT, spaceAfter=14)]
        for i, r in enumerate(ok, 1):
            a = r.article
            line = f"{i}. {a.title}"
            out.append(self.P(line, s["toc"]))
            out.append(self.P(" · ".join(x for x in (a.publication, a.author, a.date) if x), s["meta"]))
            out.append(Spacer(1, 4))
        if failed:
            out.append(Spacer(1, 12))
            out.append(Paragraph("Skipped", s["h2"]))
            for r in failed:
                out.append(self.P(f"{r.url} — {r.error}", s["err"]))
        return out

    def _article(self, r: ArticleResult):
        s, a, m = self.s, r.article, r.summary
        out = [self.P(a.title or m.headline, s["h1"])]
        if a.subtitle:
            out.append(self.P(a.subtitle, s["sub"]))
        meta = " · ".join(x for x in (a.publication, a.author, a.date, f"{a.word_count:,} words") if x)
        out += [self.P(meta, s["meta"]),
                Paragraph(f'<link href="{escape(a.url)}" color="#2f5d8a">{escape(a.url)}</link>', s["meta"]),
                Spacer(1, 8)]
        if m.tldr:
            box = Table([[self.P(m.tldr, s["body"])]], colWidths=[170 * mm])
            box.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), PANEL),
                                     ("LINEBEFORE", (0, 0), (0, -1), 3, ACCENT),
                                     ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                                     ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
            out += [Paragraph("TL;DR", s["h2"]), box]
        if m.key_points:
            out.append(Paragraph("Key points", s["h2"]))
            out += [self.P(k, s["bullet"], bulletText="•") for k in m.key_points]
        if m.takeaways:
            out.append(Paragraph("Takeaways", s["h2"]))
            out += [self.P(k, s["bullet"], bulletText="→") for k in m.takeaways]
        if m.topics:
            out += [Spacer(1, 10), self.P("Topics: " + ", ".join(m.topics), s["tag"])]
        if r.review_verdict:
            note = {"pass": "Fact-checked by the Critic agent", "revise": "Critic flagged remaining issues",
                    "skipped": ""}.get(r.review_verdict, "")
            if note:
                rounds = f" ({r.review_rounds} revision round{'s' if r.review_rounds != 1 else ''})" if r.review_rounds else ""
                out.append(Paragraph(escape(note + rounds), s["meta"]))
        return out
