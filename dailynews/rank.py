"""Keyword-based interest matching, deduplication and issue selection (no API key needed)."""

from __future__ import annotations

import re
import unicodedata
from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from .config import Config, Interest
from .models import Article

TRACKING_PARAMS = re.compile(r"^(utm_|fbclid$|gclid$|mc_|ocid$|cmpid$|ref$|src$)")


def canonical_url(url: str) -> str:
    p = urlparse(url)
    query = [(k, v) for k, v in parse_qsl(p.query) if not TRACKING_PARAMS.match(k.lower())]
    host = (p.hostname or "").removeprefix("www.")
    return urlunparse(("https", host, p.path.rstrip("/"), "", urlencode(query), ""))


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def title_key(title: str) -> str:
    # Drop trailing " - Publisher" / " | Publisher" suffixes common in aggregator titles.
    title = re.split(r"\s[-|–—]\s(?=[^-|–—]*$)", title)[0]
    return _normalize(title)


def dedupe(articles: list[Article]) -> list[Article]:
    """Keep the first article per canonical URL and per near-identical title."""
    seen_urls: set[str] = set()
    seen_titles: list[set[str]] = []
    out = []
    for a in articles:
        cu = canonical_url(a.url)
        words = set(title_key(a.title).split())
        if cu in seen_urls:
            continue
        if len(words) >= 4 and any(_jaccard(words, t) >= 0.8 for t in seen_titles):
            continue
        seen_urls.add(cu)
        seen_titles.append(words)
        out.append(a)
    return out


def _jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def _keyword_hits(keyword: str, text: str) -> int:
    kw = _normalize(keyword)
    if not kw:
        return 0
    return len(re.findall(rf"(?<![a-z0-9]){re.escape(kw)}(?![a-z0-9])", text))


def score_interest(article: Article, interest: Interest) -> tuple[float, list[str]]:
    title = _normalize(article.title)
    rest = _normalize(f"{article.summary} {article.body_html[:4000]}")
    keywords = interest.keywords or [interest.name]
    score, matched = 0.0, []
    for kw in keywords:
        t, r = _keyword_hits(kw, title), _keyword_hits(kw, rest)
        if t or r:
            matched.append(kw)
            score += 3.0 * min(t, 2) + min(r, 5)
    if article.origin_interest == interest.name:
        score += 2.0  # found by this interest's own search feed
    return score, matched


def assign(article: Article, cfg: Config, now: datetime) -> Article | None:
    """Place the article in its best-matching section, or drop it (return None)."""
    best: tuple[float, Interest | None, list[str]] = (0.0, None, [])
    for interest in cfg.interests:
        s, m = score_interest(article, interest)
        if s > best[0]:
            best = (s, interest, m)
    score, interest, matched = best
    if interest is not None and (matched or article.origin_interest == interest.name):
        article.section, article.matched = interest.name, matched
    elif article.forced_section:
        article.section = article.forced_section
        score = max(score, 1.0)
    else:
        return None
    if article.published:
        age_h = (now - article.published).total_seconds() / 3600
        score += max(0.0, 2.0 - age_h / 12)  # small freshness bonus
    article.score = score
    return article


def rank(articles: list[Article], cfg: Config, now: datetime | None = None) -> list[Article]:
    now = now or datetime.now(UTC)
    placed = [a for a in (assign(a, cfg, now) for a in articles) if a is not None]
    return sorted(placed, key=lambda a: a.score, reverse=True)


def select(ranked: list[Article], cfg: Config) -> list[Article]:
    """Cap per section and overall, then order sections as configured."""
    per_section: dict[str, int] = {}
    chosen = []
    for a in ranked:
        if per_section.get(a.section, 0) >= cfg.max_per_section:
            continue
        per_section[a.section] = per_section.get(a.section, 0) + 1
        chosen.append(a)
        if len(chosen) >= cfg.max_articles:
            break
    order = {i.name: n for n, i in enumerate(cfg.interests)}
    return sorted(chosen, key=lambda a: (order.get(a.section, len(order)), -a.score))
