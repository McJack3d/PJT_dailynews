"""Configuration: the public config.yaml plus secrets from environment variables."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator


class Interest(BaseModel):
    name: str
    keywords: list[str] = Field(default_factory=list)
    # Free-text query for a Google News search feed. Defaults to the keywords.
    search: str | None = None
    # Set to false to rely only on your hand-picked feeds for this interest.
    discover: bool = True

    @field_validator("keywords")
    @classmethod
    def _strip(cls, v: list[str]) -> list[str]:
        return [k.strip() for k in v if k.strip()]

    def search_query(self) -> str:
        if self.search:
            return self.search
        if self.keywords:
            return " OR ".join(f'"{k}"' if " " in k else k for k in self.keywords)
        return self.name


class Feed(BaseModel):
    url: str
    name: str | None = None
    # Put every recent item from this feed in the issue, even without a keyword match.
    include_all: bool = False
    # Section used for include_all items that match no interest.
    section: str | None = None


class Config(BaseModel):
    title: str = "Daily News"
    language: str = "en"
    # Region/market for news search, e.g. en-US, en-GB, fr-FR.
    market: str = "en-US"
    max_articles: int = Field(25, ge=1, le=200)
    max_per_section: int = Field(8, ge=1, le=100)
    max_age_hours: int = Field(36, ge=1)
    min_words: int = Field(150, ge=0)
    interests: list[Interest] = Field(default_factory=list)
    feeds: list[Feed] = Field(default_factory=list)

    @field_validator("feeds", mode="before")
    @classmethod
    def _feeds_from_strings(cls, v):
        return [{"url": f} if isinstance(f, str) else f for f in (v or [])]


class Secrets(BaseModel):
    kindle_email: str
    sender_email: str
    smtp_host: str
    smtp_port: int = 587
    smtp_user: str
    smtp_password: str
    # Optional: also send a copy to this address (e.g. your own inbox).
    bcc: str | None = None

    @classmethod
    def from_env(cls) -> Secrets:
        env = os.environ
        missing = [
            k for k in ("KINDLE_EMAIL", "SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD") if not env.get(k)
        ]
        if missing:
            raise SystemExit(f"Missing required environment variables: {', '.join(missing)}")
        return cls(
            kindle_email=env["KINDLE_EMAIL"],
            sender_email=env.get("SENDER_EMAIL") or env["SMTP_USER"],
            smtp_host=env["SMTP_HOST"],
            smtp_port=int(env.get("SMTP_PORT") or 587),
            smtp_user=env["SMTP_USER"],
            smtp_password=env["SMTP_PASSWORD"],
            bcc=env.get("BCC_EMAIL") or None,
        )


def load_config(path: str | Path) -> Config:
    path = Path(path)
    if not path.exists():
        raise SystemExit(f"Config file not found: {path} (copy config.example.yaml to start)")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cfg = Config.model_validate(data)
    if not cfg.interests and not cfg.feeds:
        raise SystemExit("Config needs at least one interest or feed.")
    return cfg
