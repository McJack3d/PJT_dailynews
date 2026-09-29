"""Build the daily issue as an EPUB3 that Send to Kindle accepts."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from html import escape
from itertools import groupby
from pathlib import Path
from zoneinfo import ZoneInfo

from ebooklib import epub

from . import __version__
from .cover import render_cover
from .models import Article

log = logging.getLogger(__name__)

# Kindle-safe newspaper styling: grayscale, em units, no floats or flexbox.
CSS = """
body { font-family: serif; line-height: 1.45; margin: 0 0.3em; }
a { color: #000; text-decoration: none; }
p { margin: 0; }

.masthead { text-align: center; border-top: 4px solid #000; padding-top: 3px;
  margin-bottom: 1.6em; }
.mast-title { font-size: 2.4em; font-weight: bold; line-height: 1.1; margin: 0;
  padding: 0.3em 0 0.2em; border-top: 1px solid #000; border-bottom: 1px solid #000; }
.dateline { font-size: 0.7em; letter-spacing: 0.14em; text-transform: uppercase;
  padding: 0.5em 0; border-bottom: 1px solid #000; }

.toc-section { font-size: 0.78em; font-weight: bold; letter-spacing: 0.14em;
  text-transform: uppercase; margin: 1.8em 0 0.8em; padding-bottom: 0.3em;
  border-bottom: 1px solid #000; }
.toc-item { margin: 0 0 0.9em; line-height: 1.3; }
.toc-item.lead a { font-size: 1.2em; font-weight: bold; }
.toc-meta { font-size: 0.75em; color: #555; }

.kicker { font-size: 0.7em; font-weight: bold; letter-spacing: 0.14em;
  text-transform: uppercase; margin: 0.4em 0 0.7em; }
.headline { font-size: 1.65em; font-weight: bold; line-height: 1.18; margin: 0 0 0.5em; }
.byline { font-size: 0.8em; color: #444; margin-bottom: 1.4em; padding-bottom: 0.7em;
  border-bottom: 1px solid #000; }
.byline .source { font-weight: bold; color: #000; }

.body p { text-indent: 1.3em; text-align: justify; }
.body > p:first-child, .body h2 + p, .body h3 + p, .body h4 + p, .body ul + p,
.body ol + p, .body blockquote + p, .body table + p { text-indent: 0; }
.body h2, .body h3, .body h4 { font-size: 1.05em; font-weight: bold; margin: 1.4em 0 0.4em; }
.body blockquote { margin: 0.9em 1.3em; font-style: italic; }
.body blockquote p { text-indent: 0; }
.body ul, .body ol { margin: 0.6em 0 0.8em 1.4em; padding: 0; }
.body li { margin-bottom: 0.3em; }
.body img { max-width: 100%; }
.body table { border-collapse: collapse; font-size: 0.85em; margin: 0.8em 0; }
.body td, .body th { border: 1px solid #999; padding: 0.2em; }

.end { text-align: center; letter-spacing: 0.4em; margin: 1.6em 0 1em; }
.note { font-size: 0.75em; color: #555; }
"""

_STRINGS = {
    "en": {
        "contents": "Contents",
        "articles": "articles",
        "reading": "read",
        "original": "Original article:",
        "unavailable": "Full text unavailable offline. Read it at",
        "days": "Monday Tuesday Wednesday Thursday Friday Saturday Sunday".split(),
        "months": (
            "January February March April May June July August September October November December"
        ).split(),
        "months_short": "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(),
    },
    "fr": {
        "contents": "Sommaire",
        "articles": "articles",
        "reading": "de lecture",
        "original": "Article original :",
        "unavailable": "Texte intégral indisponible hors ligne. À lire sur",
        "days": "lundi mardi mercredi jeudi vendredi samedi dimanche".split(),
        "months": (
            "janvier février mars avril mai juin juillet août septembre octobre novembre décembre"
        ).split(),
        "months_short": "janv. févr. mars avr. mai juin juil. août sept. oct. nov. déc.".split(),
    },
}


def _strings(language: str) -> dict:
    return _STRINGS.get(language.split("-")[0].lower(), _STRINGS["en"])


def _long_date(d: datetime, s: dict) -> str:
    return f"{s['days'][d.weekday()]} {d.day} {s['months'][d.month - 1]} {d.year}"


def _minutes(a: Article) -> int:
    return max(1, round(a.word_count / 230)) if a.word_count else 0


def _duration(minutes: int, s: dict) -> str:
    if minutes < 60:
        return f"{minutes} min {s['reading']}"
    h, m = divmod(minutes, 60)
    return f"{h} h {m:02d} {s['reading']}" if m else f"{h} h {s['reading']}"


def _meta_line(a: Article, s: dict, tz: ZoneInfo) -> str:
    bits = [f'<span class="source">{escape(a.source)}</span>'] if a.source else []
    if a.published:
        t = a.published.astimezone(tz)
        stamp = f"{t.day} {s['months_short'][t.month - 1]}, {t:%H:%M}"
        bits.append(stamp + (" UTC" if tz.key == "UTC" else ""))
    if a.word_count:
        bits.append(_duration(_minutes(a), s))
    return " · ".join(bits)


def _article_body(a: Article, s: dict) -> str:
    link = f'<a href="{escape(a.url)}">{escape(a.source or a.url)}</a>'
    if a.body_html:
        body, note = a.body_html, f"{s['original']} {link}"
    else:
        body = f"<p>{escape(a.summary)}</p>" if a.summary else ""
        note = f"{s['unavailable']} {link}."
    return f'<div class="body">{body}</div><p class="end">• • •</p><p class="note">{note}</p>'


def _cover(title: str, dateline: str, articles: list[Article], footer: str) -> bytes | None:
    leads = {}
    for a in articles:  # articles arrive grouped by section, best first
        leads.setdefault(a.section, (a.section, a.title, a.source))
    try:
        return render_cover(title, dateline, list(leads.values()), footer)
    except Exception:  # a missing cover must never cost the issue
        log.exception("Cover generation failed; sending without a cover")
        return None


def build_epub(
    articles: list[Article],
    *,
    title: str,
    language: str,
    date: datetime,
    out_path: str | Path,
    timezone: str = "UTC",
) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tz = ZoneInfo(timezone)
    local = date.astimezone(tz)
    s = _strings(language)
    day = local.strftime("%Y-%m-%d")
    long_date = _long_date(local, s)
    total = _duration(sum(_minutes(a) for a in articles), s)
    stats = f"{len(articles)} {s['articles']} · {total}"

    book = epub.EpubBook()
    book.set_identifier(f"dailynews-{day}-{hashlib.sha1(title.encode()).hexdigest()[:8]}")
    book.set_title(f"{title} — {long_date}")
    book.set_language(language)
    book.add_author(title)
    book.add_metadata("DC", "date", day)
    book.add_metadata("DC", "publisher", f"dailynews {__version__}")
    cover = _cover(title, long_date, articles, stats)
    if cover:
        book.set_cover("cover.jpg", cover, create_page=False)

    css = epub.EpubItem(uid="style", file_name="style.css", media_type="text/css", content=CSS)
    book.add_item(css)

    chapters: list[tuple[Article, epub.EpubHtml]] = []
    for n, a in enumerate(articles, 1):
        ch = epub.EpubHtml(title=a.title, file_name=f"a{n:03d}.xhtml", lang=language)
        ch.content = (
            f'<p class="kicker">{escape(a.section)}</p>'
            f'<h1 class="headline">{escape(a.title)}</h1>'
            f'<p class="byline">{_meta_line(a, s, tz)}</p>{_article_body(a, s)}'
        )
        ch.add_item(css)
        book.add_item(ch)
        chapters.append((a, ch))

    # Front page: masthead plus a clickable table of contents grouped by section.
    parts = [
        '<div class="masthead">',
        f'<h1 class="mast-title">{escape(title)}</h1>',
        f'<p class="dateline">{escape(long_date)} · {escape(stats)}</p>',
        "</div>",
    ]
    toc = []
    for section, group in groupby(chapters, key=lambda pair: pair[0].section):
        group = list(group)
        parts.append(f'<h2 class="toc-section">{escape(section)}</h2>')
        for i, (a, ch) in enumerate(group):
            meta = [escape(a.source)] if a.source else []
            if a.word_count:
                meta.append(f"{_minutes(a)} min")
            parts.append(
                f'<p class="toc-item{" lead" if i == 0 else ""}">'
                f'<a href="{ch.file_name}">{escape(a.title)}</a><br/>'
                f'<span class="toc-meta">{" · ".join(meta)}</span></p>'
            )
        toc.append((epub.Section(section, href=group[0][1].file_name), [ch for _, ch in group]))

    front = epub.EpubHtml(title=s["contents"], file_name="front.xhtml", lang=language)
    front.content = "".join(parts)
    front.add_item(css)
    book.add_item(front)

    book.toc = [epub.Link("front.xhtml", s["contents"], "front"), *toc]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = [front] + [ch for _, ch in chapters]
    book.guide = [{"type": "toc", "title": s["contents"], "href": "front.xhtml"}]

    epub.write_epub(str(out_path), book)
    return out_path
