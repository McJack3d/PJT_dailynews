import smtplib
import zipfile

from dailynews import deliver, pipeline
from dailynews.config import Secrets
from dailynews.extract import count_words, sanitize_html
from dailynews.sources import parse_feed
from dailynews.state import SeenStore

from .conftest import FIXTURES, NOW


def fake_extract(articles):
    body = sanitize_html("".join(f"<p>{'word ' * 60}</p>" for _ in range(3)))
    for a in articles:
        if "llm" in a.url:
            a.body_html, a.word_count = body, count_words(body)
    return articles


def test_build_issue_end_to_end(cfg, tmp_path, monkeypatch):
    monkeypatch.setattr(
        pipeline, "collect", lambda c, now: parse_feed((FIXTURES / "feed.xml").read_bytes())
    )
    monkeypatch.setattr(pipeline, "extract_all", fake_extract)
    seen = SeenStore(tmp_path / "seen.json")
    seen.add(["https://example.com/spacex"])  # already delivered yesterday

    path, articles = pipeline.build_issue(cfg, seen, tmp_path, NOW)

    assert path.name == "dailynews-2026-09-28.epub"
    assert [a.title for a in articles] == ["New LLM beats benchmarks in machine learning test"]
    assert articles[0].word_count == 180
    with zipfile.ZipFile(path) as z:
        assert "word word" in z.read("EPUB/a001.xhtml").decode()
    assert "LLM" in pipeline.summary_markdown(articles, path)


def test_build_issue_with_nothing_matching(cfg, tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "collect", lambda c, now: [])
    path, articles = pipeline.build_issue(cfg, SeenStore(tmp_path / "s.json"), tmp_path, NOW)
    assert path is None and articles == []


def test_send_uses_starttls_and_masks_address(tmp_path, monkeypatch, caplog):
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            sent["host"] = (host, port)

        def starttls(self, context):
            sent["tls"] = True

        def login(self, user, pw):
            sent["login"] = user

        def send_message(self, msg):
            sent["msg"] = msg

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    epub = tmp_path / "x.epub"
    epub.write_bytes(b"PK fake")
    secrets = Secrets(
        kindle_email="reader_123@kindle.com",
        sender_email="me@example.com",
        smtp_host="smtp.example.com",
        smtp_user="me@example.com",
        smtp_password="pw",
    )
    caplog.set_level("INFO")
    deliver.send(epub, secrets, subject="Daily")

    assert sent["host"] == ("smtp.example.com", 587) and sent["tls"]
    msg = sent["msg"]
    assert msg["To"] == "reader_123@kindle.com"
    att = next(msg.iter_attachments())
    assert att.get_content_type() == "application/epub+zip"
    assert att.get_filename() == "x.epub"
    assert "reader_123" not in caplog.text and "re***@kindle.com" in caplog.text
