import json
from datetime import timedelta

from dailynews.state import SeenStore

from .conftest import NOW


def test_roundtrip_and_prune(tmp_path):
    path = tmp_path / "seen.json"
    store = SeenStore(path)
    store.add(["https://ex.com/old"], when=NOW - timedelta(days=40))
    store.add(["https://www.ex.com/new?utm_source=x"], when=NOW)
    store.save(NOW)

    reloaded = SeenStore(path)
    assert "https://ex.com/new" in reloaded  # canonicalised
    assert "https://ex.com/old" not in reloaded  # pruned after 30 days
    raw = path.read_text()
    assert "ex.com" not in raw  # only hashes are stored
    assert json.loads(raw)["updated"].startswith("2026-09-28")


def test_missing_file_is_empty(tmp_path):
    assert "https://x.com" not in SeenStore(tmp_path / "nope.json")


def test_updated_roundtrip(tmp_path):
    from datetime import UTC, datetime

    from dailynews.state import SeenStore

    path = tmp_path / "seen.json"
    assert SeenStore(path).updated is None
    now = datetime(2026, 9, 29, 4, 40, tzinfo=UTC)
    store = SeenStore(path)
    store.save(now)
    assert SeenStore(path).updated == now
