from dailynews.models import Article
from dailynews.rank import canonical_url, dedupe, rank, select

from .conftest import NOW


def art(title, url=None, **kw):
    return Article(url=url or f"https://ex.com/{abs(hash(title))}", title=title, source="Ex", **kw)


def test_canonical_url_drops_tracking():
    a = canonical_url("http://www.ex.com/a/?utm_source=rss&id=3#frag")
    assert a == "https://ex.com/a?id=3"


def test_dedupe_by_url_and_similar_title():
    items = [
        art("SpaceX schedules next big rocket launch", "https://ex.com/a?utm_medium=x"),
        art("Other", "https://www.ex.com/a"),
        art("SpaceX schedules next big rocket launch - Reuters", "https://b.com/z"),
        art("Completely different story about rockets", "https://c.com/y"),
    ]
    assert [a.url for a in dedupe(items)] == ["https://ex.com/a?utm_medium=x", "https://c.com/y"]


def test_rank_assigns_sections_and_drops_unmatched(cfg):
    items = [
        art("Bakery wins award"),
        art("SpaceX rocket launch delayed"),
        art("LLM tops machine learning charts", summary="A new LLM."),
        art("Unrelated but discovered", origin_interest="Space"),
    ]
    ranked = rank(items, cfg, NOW)
    by_title = {a.title: a.section for a in ranked}
    assert "Bakery wins award" not in by_title
    assert by_title["SpaceX rocket launch delayed"] == "Space"
    assert by_title["LLM tops machine learning charts"] == "AI"
    assert by_title["Unrelated but discovered"] == "Space"
    assert ranked[0].title == "LLM tops machine learning charts"


def test_forced_section_for_include_all_feeds(cfg):
    ranked = rank([art("Bakery wins award", forced_section="Local")], cfg, NOW)
    assert ranked[0].section == "Local"


def test_select_caps_and_orders_by_interest(cfg):
    cfg.max_per_section = 2
    items = [art(f"LLM story {i}", section="AI", score=10 - i) for i in range(5)]
    items += [art("SpaceX story", section="Space", score=20)]
    chosen = select(sorted(items, key=lambda a: -a.score), cfg)
    assert [a.section for a in chosen] == ["AI", "AI", "Space"]
