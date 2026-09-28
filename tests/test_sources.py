import json

import httpx
import pytest

from dailynews.config import Interest
from dailynews.sources import news_search_url, parse_feed, resolve_google_news, strip_html

from .conftest import FIXTURES

GOOGLE_ITEM = b"""<?xml version="1.0"?><rss version="2.0"><channel>
<title>"SpaceX" - Google News</title>
<item><title>SpaceX readies Starship - Reuters</title>
<link>https://news.google.com/rss/articles/CBMiABC?oc=5</link>
<pubDate>Mon, 28 Sep 2026 06:00:00 GMT</pubDate>
<description>&lt;a href="https://news.google.com/rss/articles/CBMiABC"&gt;
SpaceX readies Starship&lt;/a&gt;&amp;nbsp;&amp;nbsp;&lt;font color="#6f6f6f"&gt;
Reuters&lt;/font&gt;</description>
<source url="https://www.reuters.com">Reuters</source></item></channel></rss>"""


def test_parse_feed_reads_items_and_strips_html():
    items = parse_feed((FIXTURES / "feed.xml").read_bytes())
    assert len(items) == 4
    first = items[0]
    assert first.title == "New LLM beats benchmarks in machine learning test"
    assert first.summary == "A new LLM was released today."
    assert first.source == "Example Tech"
    assert first.published.isoformat() == "2026-09-28T06:00:00+00:00"
    assert first.discovered_url == first.url


def test_parse_google_news_item():
    (item,) = parse_feed(GOOGLE_ITEM, origin_interest="Space")
    assert item.title == "SpaceX readies Starship"
    assert item.source == "Reuters"
    assert item.summary == ""
    assert item.origin_interest == "Space"


def test_search_url():
    interest = Interest(name="AI", keywords=["machine learning", "LLM"])
    url = news_search_url(interest, "fr-FR", max_age_hours=36)
    assert url.startswith("https://news.google.com/rss/search?q=")
    assert "%22machine+learning%22+OR+LLM+when%3A2d" in url
    assert url.endswith("&hl=fr-FR&gl=FR&ceid=FR:fr")


def _google_transport(target):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            assert request.url.path == "/rss/articles/CBMiABC"
            page = '<html><c-wiz><div jscontroller="x" data-n-a-sg="SIG" data-n-a-ts="123">'
            return httpx.Response(200, text=page + "</div></c-wiz></html>")
        form = dict(httpx.QueryParams(request.content.decode()))
        inner = json.loads(form["f.req"])[0][0][1]
        assert '"CBMiABC",123,"SIG"' in inner
        payload = json.dumps([["wrb.fr", "Fbv4je", json.dumps(["garturlres", target, 1])]])
        return httpx.Response(200, text=")]}'\n\n" + payload)

    return httpx.MockTransport(handler)


def test_resolve_google_news():
    target = "https://www.reuters.com/space/starship-2026-09-28/"
    with httpx.Client(transport=_google_transport(target)) as client:
        url = "https://news.google.com/rss/articles/CBMiABC?oc=5"
        assert resolve_google_news(client, url) == target


def test_resolve_google_news_rejects_garbage():
    with httpx.Client(transport=_google_transport(None)) as client:
        with pytest.raises(ValueError):
            resolve_google_news(client, "https://news.google.com/rss/articles/CBMiABC")


def test_strip_html_handles_plain_text():
    assert strip_html("plain") == "plain"
    assert strip_html("<p>a <i>b</i></p>") == "a b"
