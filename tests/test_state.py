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
