"""Collect candidate articles from RSS/Atom feeds and per-interest news search feeds."""

from __future__ import annotations

import calendar
import json
import logging
import math
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from urllib.parse import quote_plus, urlparse

import feedparser
import httpx
from lxml import html as lxml_html

from . import USER_AGENT
from .config import Config, Feed, Interest
from .models import Article

log = logging.getLogger(__name__)

TIMEOUT = httpx.Timeout(20.0)


def news_search_url(interest: Interest, market: str, max_age_hours: int) -> str:
    """Google News RSS search for one interest, limited to recent articles."""
    lang, _, country = market.partition("-")
    country = (country or lang).upper()
    days = max(1, math.ceil(max_age_hours / 24))
    query = quote_plus(f"{interest.search_query()} when:{days}d")
    return (
        f"https://news.google.com/rss/search?q={query}"
        f"&hl={quote_plus(market)}&gl={country}&ceid={country}:{lang}"
    )


def is_google_news(url: str) -> bool:
    return urlparse(url).hostname == "news.google.com"


def resolve_google_news(client: httpx.Client, url: str) -> str:
    """Google News RSS links are opaque redirects. Resolve one to the publisher URL the way
    the news.google.com page does: read the article's signature and timestamp from its page,
    then ask the batchexecute endpoint for the target. Raises on any failure."""
    article_id = urlparse(url).path.rstrip("/").split("/")[-1]
    page = client.get(f"https://news.google.com/rss/articles/{article_id}")
    page.raise_for_status()
    node = lxml_html.fromstring(page.text).xpath("//*[@data-n-a-sg][@data-n-a-ts]")
    if not node:
        raise ValueError("Google News page had no decoding parameters")
    sig, ts = node[0].get("data-n-a-sg"), node[0].get("data-n-a-ts")
    inner = (
        '["garturlreq",[["X","X",["X","X"],null,null,1,1,"US:en",null,1,null,null,null,'
        f'null,null,0,1],"X","X",1,[1,1,1],1,1,null,0,0,null,0],"{article_id}",{ts},"{sig}"]'
    )
    resp = client.post(
        "https://news.google.com/_/DotsSplashUi/data/batchexecute",
        data={"f.req": json.dumps([[["Fbv4je", inner, None, "generic"]]])},
    )
    resp.raise_for_status()
    body = resp.text.split("\n\n", 1)[1]
    target = json.loads(json.loads(body)[0][2])[1]
    if not isinstance(target, str) or not target.startswith("http"):
        raise ValueError(f"Unexpected Google News response: {target!r}")
    return target


def strip_html(text: str) -> str:
    if not text or "<" not in text:
        return (text or "").strip()
    try:
        return " ".join(lxml_html.fromstring(text).text_content().split())
    except Exception:  # malformed markup; the summary is best-effort anyway
        return text.strip()


def _entry_time(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            return datetime.fromtimestamp(calendar.timegm(t), tz=UTC)
    return None


def parse_feed(
    content: bytes,
    *,
    feed_name: str | None = None,
    origin_interest: str | None = None,
    forced_section: str | None = None,
) -> list[Article]:
    parsed = feedparser.parse(content)
    default_source = feed_name or parsed.feed.get("title") or ""
    articles = []
    for entry in parsed.entries:
        link = entry.get("link")
        title = strip_html(entry.get("title", ""))
        if not link or not title:
            continue
        summary = strip_html(entry.get("summary", ""))
        # Aggregators such as Google News name the publisher per item.
        source = (entry.get("source") or {}).get("title")
        if source:
            title = title.removesuffix(f" - {source}")
        if is_google_news(link):
            summary = ""  # just the headline and outlet again; the real text comes later
        articles.append(
            Article(
                url=link,
                title=title,
                source=source or default_source or urlparse(link).hostname or "",
                published=_entry_time(entry),
                summary=summary,
                origin_interest=origin_interest,
                forced_section=forced_section,
            )
        )
    return articles


def _fetch(client: httpx.Client, url: str) -> bytes | None:
    try:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.content
    except httpx.HTTPError as e:
        reason = (str(e) or type(e).__name__).splitlines()[0]  # drop httpx's MDN hint
        log.warning("Feed failed: %s (%s)", url, reason)
        return None


def _jobs(cfg: Config) -> Iterable[tuple[str, dict]]:
    for feed in cfg.feeds:
        yield feed.url, _feed_kwargs(feed)
    for interest in cfg.interests:
        if interest.discover:
            url = news_search_url(interest, cfg.market, cfg.max_age_hours)
            yield url, {"origin_interest": interest.name}


def _feed_kwargs(feed: Feed) -> dict:
    section = (feed.section or feed.name or "News") if feed.include_all else None
    return {"feed_name": feed.name, "forced_section": section}


def is_fresh(article: Article, now: datetime, max_age_hours: int) -> bool:
    return article.published is None or article.published >= now - timedelta(hours=max_age_hours)


def collect(cfg: Config, now: datetime | None = None) -> list[Article]:
    """Fetch every configured source in parallel. A failing source never fails the issue."""
    now = now or datetime.now(UTC)
    jobs = list(_jobs(cfg))
    headers = {"User-Agent": USER_AGENT}
    with httpx.Client(headers=headers, timeout=TIMEOUT, follow_redirects=True) as client:
        with ThreadPoolExecutor(max_workers=8) as pool:
            contents = list(pool.map(lambda j: _fetch(client, j[0]), jobs))

    articles: list[Article] = []
    for (url, kwargs), content in zip(jobs, contents, strict=True):
        if content is None:
            continue
        items = parse_feed(content, **kwargs)
        fresh = sum(is_fresh(a, now, cfg.max_age_hours) for a in items)
        log.info("%3d fresh / %3d items  %s", fresh, len(items), url)
        articles.extend(items)
    return articles
