"""Fetch full article text and turn it into clean, e-reader friendly XHTML."""

from __future__ import annotations

import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx
import trafilatura
from lxml import etree
from lxml import html as lxml_html

from . import USER_AGENT
from .models import Article
from .rank import title_key
from .sources import is_google_news, resolve_google_news

log = logging.getLogger(__name__)

ALLOWED = {
    "p", "h3", "h4", "ul", "ol", "li", "blockquote", "em", "strong", "b", "i",
    "br", "pre", "code", "table", "thead", "tbody", "tr", "th", "td", "sub", "sup",
}  # fmt: skip
RENAME = {"h1": "h3", "h2": "h3", "h5": "h4", "h6": "h4", "del": "s"}
DROP_WITH_CONTENT = {"script", "style", "iframe", "noscript", "form", "button", "svg", "figure"}


def sanitize_html(fragment: str) -> str:
    """Whitelist tags, drop every attribute, and serialize as well-formed XHTML."""
    if not fragment.strip():
        return ""
    root = lxml_html.fragment_fromstring(fragment, create_parent="div")
    for el in list(root.iter()):
        if el is root:
            continue
        if not isinstance(el.tag, str):  # comments, processing instructions
            el.drop_tree()
            continue
        tag = RENAME.get(el.tag, el.tag)
        el.tag = tag
        el.attrib.clear()
        if tag in DROP_WITH_CONTENT:
            el.drop_tree()
        elif tag not in ALLOWED:
            el.drop_tag()
    # Drop empty paragraphs left behind by removed media.
    for p in root.findall(".//p"):
        if not (p.text_content() or "").strip() and not len(p):
            p.drop_tree()
    parts = [etree.tostring(child, method="xml", encoding="unicode") for child in root]
    lead = (root.text or "").strip()
    out = "".join(parts)
    if lead:
        out = f"<p>{_escape(lead)}</p>" + out
    return out


def drop_repeated_title(fragment: str, title: str) -> str:
    """Pages often restate the headline as the first line of the body; the issue already
    prints it, so drop that first block when it matches the title."""
    if not fragment:
        return fragment
    root = lxml_html.fragment_fromstring(fragment, create_parent="div")
    first = root[0] if len(root) else None
    if first is not None and not (root.text or "").strip():
        head, want = title_key(first.text_content()), title_key(title)
        if head and len(head.split()) >= 3 and (head == want or head in want or want in head):
            root.remove(first)
            return "".join(etree.tostring(c, method="xml", encoding="unicode") for c in root)
    return fragment


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def text_to_html(text: str) -> str:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]
    return "".join(f"<p>{_escape(p)}</p>" for p in paras)


def count_words(fragment: str) -> int:
    if not fragment:
        return 0
    text = lxml_html.fragment_fromstring(fragment, create_parent="div").text_content()
    return len(text.split())


class RobotsCache:
    """Per-host robots.txt check. Unreachable robots.txt means allowed, as crawlers do."""

    def __init__(self, client: httpx.Client):
        self.client = client
        self.cache: dict[str, RobotFileParser | None] = {}
        self.lock = threading.Lock()

    def allowed(self, url: str) -> bool:
        p = urlparse(url)
        base = f"{p.scheme}://{p.netloc}"
        with self.lock:
            known = base in self.cache
            rp = self.cache.get(base)
        if not known:
            rp = None
            try:
                resp = self.client.get(base + "/robots.txt")
                if resp.status_code == 200:
                    rp = RobotFileParser()
                    rp.parse(resp.text.splitlines())
            except httpx.HTTPError:
                pass
            with self.lock:
                self.cache[base] = rp
        return rp is None or rp.can_fetch(USER_AGENT, url)


def extract_one(client: httpx.Client, robots: RobotsCache, article: Article) -> Article:
    body = ""
    if is_google_news(article.url):
        try:
            article.url = resolve_google_news(client, article.url)
        except Exception as e:
            log.info("Could not resolve Google News link %s: %s", article.url, _first_line(e))
            article.body_html, article.word_count = "", 0
            return article
    if robots.allowed(article.url):
        try:
            resp = client.get(article.url)
            resp.raise_for_status()
            if "html" in resp.headers.get("content-type", "html"):
                article.url = str(resp.url)  # canonical after redirects
                extracted = trafilatura.extract(
                    resp.text,
                    url=article.url,
                    output_format="html",
                    include_comments=False,
                    include_images=False,
                    include_links=False,
                    include_tables=True,
                    favor_precision=True,
                )
                body = drop_repeated_title(sanitize_html(extracted or ""), article.title)
        except Exception as e:  # one broken page must never sink the whole issue
            log.info("Extraction failed for %s: %s", article.url, _first_line(e))
    else:
        log.info("robots.txt disallows %s", article.url)
    article.body_html = body
    article.word_count = count_words(body)
    return article


def extract_all(articles: list[Article]) -> list[Article]:
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
    timeout = httpx.Timeout(20.0)
    # From EU IPs Google redirects news.google.com to a consent page, which breaks
    # link resolution. This cookie records "reject all" and is only sent to Google.
    cookies = httpx.Cookies()
    cookies.set("SOCS", "CAI", domain=".google.com")
    with httpx.Client(
        headers=headers, cookies=cookies, timeout=timeout, follow_redirects=True
    ) as client:
        robots = RobotsCache(client)
        with ThreadPoolExecutor(max_workers=8) as pool:
            return list(pool.map(lambda a: extract_one(client, robots, a), articles))


def _first_line(e: Exception) -> str:
    """httpx errors append a multi-line MDN hint; keep logs to one line per article."""
    text = str(e) or type(e).__name__
    return text.splitlines()[0]
