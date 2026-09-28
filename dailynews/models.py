from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Article:
    url: str
    title: str
    source: str
    published: datetime | None = None
    summary: str = ""
    # Interest name the article was discovered for (news search feeds), if any.
    origin_interest: str | None = None
    # Feed-level include_all section, if any.
    forced_section: str | None = None
    # Filled in by extraction: sanitized XHTML body fragment.
    body_html: str = ""
    word_count: int = 0
    # Filled in by ranking.
    section: str = ""
    score: float = 0.0
    matched: list[str] = field(default_factory=list)
    # The link as found in the feed; `url` may later change to the resolved publisher URL.
    discovered_url: str = ""

    def __post_init__(self) -> None:
        self.discovered_url = self.discovered_url or self.url
