import os
import subprocess
import zipfile

import pytest
from lxml import etree

from dailynews.epub import build_epub
from dailynews.models import Article

from .conftest import NOW


def sample_articles():
    return [
        Article(
            url="https://ex.com/a?x=1&y=2",
            title="Tom & Jerry <review>",
            source="Ex & Co",
            published=NOW,
            section="AI",
            body_html="<h3>Part</h3><p>Body text.</p><ul><li>one</li></ul>",
            word_count=500,
        ),
        Article(
            url="https://ex.com/b",
            title="Paywalled story",
            source="Paper",
            section="Space",
            summary="Only the summary is available.",
        ),
    ]


def test_build_epub_structure(tmp_path):
    path = build_epub(
        sample_articles(), title="Test Daily", language="en", date=NOW, out_path=tmp_path / "t.epub"
    )
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        assert names[0] == "mimetype"
        assert "EPUB/front.xhtml" in names and "EPUB/a001.xhtml" in names
        for name in names:
            if name.endswith((".xhtml", ".opf", ".ncx")):
                etree.fromstring(z.read(name))  # every document is well-formed XML
        front = z.read("EPUB/front.xhtml").decode()
        assert "Tom &amp; Jerry &lt;review&gt;" in front
        assert "Space" in front
        paywalled = z.read("EPUB/a002.xhtml").decode()
        assert "Only the summary is available." in paywalled
        opf = z.read("EPUB/content.opf").decode()
        assert "Test Daily — Mon 28 Sep 2026" in opf


@pytest.mark.skipif(not os.environ.get("EPUBCHECK_JAR"), reason="EPUBCHECK_JAR not set")
def test_epubcheck_passes(tmp_path):
    path = build_epub(
        sample_articles(), title="Test Daily", language="en", date=NOW, out_path=tmp_path / "t.epub"
    )
    result = subprocess.run(
        ["java", "-jar", os.environ["EPUBCHECK_JAR"], str(path)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr
