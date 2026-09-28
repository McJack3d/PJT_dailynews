from datetime import UTC, datetime
from pathlib import Path

import pytest

from dailynews.config import Config

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 9, 28, 8, 0, tzinfo=UTC)


@pytest.fixture
def cfg() -> Config:
    return Config.model_validate(
        {
            "title": "Test Daily",
            "interests": [
                {"name": "AI", "keywords": ["LLM", "machine learning"]},
                {"name": "Space", "keywords": ["SpaceX", "rocket launch"]},
            ],
            "feeds": ["https://example.com/feed.xml"],
            "min_words": 100,
        }
    )
