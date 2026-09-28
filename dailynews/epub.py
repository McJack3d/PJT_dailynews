"""Build the daily issue as an EPUB3 that Send to Kindle accepts."""

from __future__ import annotations

import hashlib
from datetime import datetime
from html import escape
from itertools import groupby
from pathlib import Path

from ebooklib import epub

from . import __version__
from .models import Article

CSS = """
body { font-family: serif; line-height: 1.4; margin: 0 0.4em; }
h1 { font-size: 1.5em; line-height: 1.2; margin: 0.6em 0 0.3em; }
h2 { font-size: 1.25em; margin: 1.2em 0 0.4em; border-bottom: 1px solid #000; }
h3, h4 { font-size: 1.1em; margin: 1em 0 0.3em; }
p { margin: 0 0 0.7em; text-align: justify; }
blockquote { margin: 0.6em 1.2em; font-style: italic; }
.meta { font-size: 0.85em; font-style: italic; margin-bottom: 1.2em; }
.note { font-size: 0.85em; margin-top: 1.5em; border-top: 1px solid #999; padding-top: 0.4em; }
.toc-section { font-weight: bold; margin-top: 1em; }
.toc-item { margin: 0 0 0.35em 1em; }
.toc-source { font-size: 0.8em; font-style: italic; }
table { border-collapse: collapse; font-size: 0.85em; }
td, th { border: 1px solid #999; padding: 0.2em; }
"""


def _meta_line(a: Article) -> str:
    bits = [escape(a.source)] if a.source else []
    if a.published:
        bits.append(a.published.strftime("%d %b %Y, %H:%M UTC"))
    if a.word_count:
        bits.append(f"{max(1, round(a.word_count / 230))} min read")
    return " · ".join(bits)


def _article_body(a: Article) -> str:
    if a.body_html:
        note = f'Original article: <a href="{escape(a.url)}">{escape(a.source or a.url)}</a>'
        return a.body_html + f'<p class="note">{note}</p>'
    summary = f"<p>{escape(a.summary)}</p>" if a.summary else ""
    note = (
        f'Full text unavailable offline. Read it at <a href="{escape(a.url)}">'
        f"{escape(a.source or a.url)}</a>."
    )
    return summary + f'<p class="note">{note}</p>'


def build_epub(
    articles: list[Article],
    *,
    title: str,
    language: str,
    date: datetime,
    out_path: str | Path,
) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    day = date.strftime("%Y-%m-%d")
    full_title = f"{title} — {date.strftime('%a %d %b %Y')}"

    book = epub.EpubBook()
    book.set_identifier(f"dailynews-{day}-{hashlib.sha1(title.encode()).hexdigest()[:8]}")
    book.set_title(full_title)
    book.set_language(language)
    book.add_author("dailynews")
    book.add_metadata("DC", "date", day)
    book.add_metadata("DC", "publisher", f"dailynews {__version__}")

    css = epub.EpubItem(uid="style", file_name="style.css", media_type="text/css", content=CSS)
    book.add_item(css)

    chapters: list[tuple[Article, epub.EpubHtml]] = []
    for n, a in enumerate(articles, 1):
        ch = epub.EpubHtml(title=a.title, file_name=f"a{n:03d}.xhtml", lang=language)
        ch.content = (
            f'<h1>{escape(a.title)}</h1><p class="meta">{_meta_line(a)}</p>{_article_body(a)}'
        )
        ch.add_item(css)
        book.add_item(ch)
        chapters.append((a, ch))

    # Front page: date plus a clickable table of contents grouped by section.
    parts = [
        f"<h1>{escape(title)}</h1>",
        f'<p class="meta">{date.strftime("%A %d %B %Y")} · {len(articles)} articles</p>',
    ]
    toc = []
    for section, group in groupby(chapters, key=lambda pair: pair[0].section):
        group = list(group)
        parts.append(f'<p class="toc-section">{escape(section)}</p>')
        for a, ch in group:
            parts.append(
                f'<p class="toc-item"><a href="{ch.file_name}">{escape(a.title)}</a> '
                f'<span class="toc-source">{escape(a.source)}</span></p>'
            )
        toc.append((epub.Section(section, href=group[0][1].file_name), [ch for _, ch in group]))

    front = epub.EpubHtml(title="Contents", file_name="front.xhtml", lang=language)
    front.content = "".join(parts)
    front.add_item(css)
    book.add_item(front)

    book.toc = [epub.Link("front.xhtml", "Contents", "front"), *toc]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = [front] + [ch for _, ch in chapters]
    book.guide = [{"type": "toc", "title": "Contents", "href": "front.xhtml"}]

    epub.write_epub(str(out_path), book)
    return out_path
