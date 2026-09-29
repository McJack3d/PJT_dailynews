"""Command line: `python -m dailynews run|preview|test-email`."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import Secrets, load_config
from .deliver import send
from .epub import build_epub
from .models import Article
from .pipeline import build_issue, summary_markdown
from .state import SeenStore


def _write_step_summary(text: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(text)


def cmd_run(args, send_it: bool) -> int:
    cfg = load_config(args.config)
    secrets = Secrets.from_env() if send_it else None  # fail fast before any fetching
    seen = SeenStore(args.state)
    now = datetime.now(UTC)
    if getattr(args, "once_per_day", False) and seen.updated:
        tz = ZoneInfo(cfg.timezone)
        if seen.updated.astimezone(tz).date() == now.astimezone(tz).date():
            logging.info("Today's issue was already sent at %s; skipping.", seen.updated)
            return 0
    epub_path, articles = build_issue(cfg, seen, args.out, now)
    _write_step_summary(summary_markdown(articles, epub_path))
    if not epub_path:
        return 0
    if not send_it:
        print(epub_path)
        return 0
    send(epub_path, secrets, subject=f"{cfg.title} {now:%Y-%m-%d}")
    seen.add(u for a in articles for u in {a.url, a.discovered_url})
    seen.save(now)
    return 0


def cmd_test_email(args) -> int:
    secrets = Secrets.from_env()
    now = datetime.now(UTC)
    sample = Article(
        url="https://github.com/McJack3d/dailynews",
        title="dailynews is set up",
        source="dailynews",
        published=now,
        section="Setup",
        body_html=(
            "<p>If you are reading this on your Kindle, delivery works: your sender address "
            "is on the approved list and the SMTP credentials are correct.</p>"
            "<p>Your first real issue will arrive on the next scheduled run.</p>"
        ),
        word_count=40,
    )
    path = build_epub(
        [sample],
        title="dailynews test",
        language="en",
        date=now,
        out_path=Path(args.out) / "dailynews-test.epub",
    )
    send(path, secrets, subject="dailynews test")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dailynews", description=__doc__)
    parser.add_argument("-c", "--config", default="config.yaml")
    parser.add_argument("--state", default="state/seen.json")
    parser.add_argument("--out", default="out")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="build today's issue and email it to your Kindle")
    run.add_argument(
        "--once-per-day",
        action="store_true",
        help="skip if an issue was already sent today (for backup schedules)",
    )
    sub.add_parser("preview", help="build today's issue locally without sending")
    sub.add_parser("test-email", help="send a one-page test issue to check delivery")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    logging.getLogger("trafilatura").setLevel(logging.ERROR)  # per-page chatter

    if args.command == "test-email":
        return cmd_test_email(args)
    return cmd_run(args, send_it=args.command == "run")


if __name__ == "__main__":
    sys.exit(main())
