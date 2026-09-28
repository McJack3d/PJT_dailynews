import trafilatura

from dailynews.extract import count_words, sanitize_html

from .conftest import FIXTURES


def test_sanitize_whitelists_tags_and_strips_attributes():
    dirty = (
        '<h1 id="x">Title</h1><p class="a" onclick="evil()">Hi <span>there</span>'
        '<script>bad()</script></p><img src="x.png"><div><p>Kept</p></div><!-- c -->'
    )
    clean = sanitize_html(dirty)
    assert clean == "<h3>Title</h3><p>Hi there</p><p>Kept</p>"


def test_sanitize_output_is_well_formed_xml():
    from lxml import etree

    clean = sanitize_html("<p>a & b<br>c</p><ul><li>x<li>y</ul>")
    etree.fromstring(f"<div>{clean}</div>")  # raises if not well-formed
    assert "<br/>" in clean


def test_trafilatura_extracts_article_body():
    html = (FIXTURES / "article.html").read_text()
    body = sanitize_html(trafilatura.extract(html, output_format="html", favor_precision=True))
    words = count_words(body)
    assert words > 150
    assert "Privacy" not in body and "track()" not in body
