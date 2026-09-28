"""Remember which articles were already delivered, so no story is sent twice.

Only truncated SHA-256 hashes of canonical URLs are stored, since this file is
committed to a (usually public) repository. The daily commit also counts as repository
activity, which stops GitHub from disabling the schedule after 60 idle days."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .rank import canonical_url

KEEP_DAYS = 30


def url_hash(url: str) -> str:
    return hashlib.sha256(canonical_url(url).encode()).hexdigest()[:16]


class SeenStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.entries: dict[str, str] = {}
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8") or "{}")
            self.entries = data.get("seen", {})

    def __contains__(self, url: str) -> bool:
        return url_hash(url) in self.entries

    def add(self, urls, when: datetime | None = None) -> None:
        stamp = (when or datetime.now(UTC)).date().isoformat()
        for url in urls:
            self.entries[url_hash(url)] = stamp

    def save(self, now: datetime | None = None) -> None:
        cutoff = ((now or datetime.now(UTC)) - timedelta(days=KEEP_DAYS)).date().isoformat()
        kept = {h: d for h, d in sorted(self.entries.items()) if d >= cutoff}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        stamp = (now or datetime.now(UTC)).isoformat(timespec="seconds")
        payload = {"updated": stamp, "seen": kept}
        self.path.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
