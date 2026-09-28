"""collect → skip already-sent → dedupe → rank → extract → select → EPUB."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from .config import Config
from .epub import build_epub
from .extract import extract_all
from .models import Article
from .rank import dedupe, rank, select
from .sources import collect, is_fresh
from .state import SeenStore

log = logging.getLogger(__name__)

# Extract more candidates than needed: paywalls and robots.txt will knock some out.
CANDIDATE_FACTOR = 2


def build_issue(
    cfg: Config, seen: SeenStore, out_dir: str | Path, now: datetime | None = None
) -> tuple[Path | None, list[Article]]:
    now = now or datetime.now(UTC)
    raw = collect(cfg, now)
    fresh = [a for a in raw if is_fresh(a, now, cfg.max_age_hours) and a.url not in seen]
    unique = dedupe(fresh)
    log.info("Collected %d items, %d recent+unsent, %d unique", len(raw), len(fresh), len(unique))

    # Cap per section so a busy section can't crowd a quieter one out of extraction.
    candidates, per_section = [], {}
    for a in rank(unique, cfg, now):
        if per_section.get(a.section, 0) < cfg.max_per_section * CANDIDATE_FACTOR:
            per_section[a.section] = per_section.get(a.section, 0) + 1
            candidates.append(a)
    log.info("Extracting full text for %d candidates", len(candidates))
    extracted = extract_all(candidates)

    # Resolved publisher URLs can reveal repeats that the feed links hid.
    extracted = [a for a in extracted if a.url not in seen]
    extracted = dedupe(sorted(extracted, key=lambda a: a.word_count, reverse=True))

    usable = []
    for a in extracted:
        if a.word_count < cfg.min_words:
            a.body_html, a.word_count = "", 0  # a stub reads worse than the summary
            if not a.summary:
                continue
        usable.append(a)
    ranked = rank(usable, cfg, now)
    for a in ranked:
        if not a.body_html:
            a.score *= 0.5  # prefer articles we can actually show in full
    chosen = select(sorted(ranked, key=lambda a: a.score, reverse=True), cfg)
    if not chosen:
        log.warning("No articles matched today; nothing to build.")
        return None, []

    out = Path(out_dir) / f"dailynews-{now:%Y-%m-%d}.epub"
    build_epub(chosen, title=cfg.title, language=cfg.language, date=now, out_path=out)
    full = sum(1 for a in chosen if a.body_html)
    log.info("Built %s: %d articles (%d full text)", out, len(chosen), full)
    return out, chosen


def summary_markdown(articles: list[Article], epub_path: Path | None) -> str:
    if not epub_path:
        return "### dailynews\nNo matching articles today; nothing was sent.\n"
    lines = [
        f"### dailynews: {epub_path.name}",
        "",
        "| Section | Title | Source | Words |",
        "|---|---|---|---|",
    ]
    for a in articles:
        title = a.title.replace("|", "\\|")
        lines.append(f"| {a.section} | [{title}]({a.url}) | {a.source} | {a.word_count or '—'} |")
    return "\n".join(lines) + "\n"
