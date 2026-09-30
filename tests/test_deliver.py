from dailynews.config import Secrets
from dailynews.deliver import build_message


def test_message_has_standard_headers(tmp_path):
    epub = tmp_path / "issue.epub"
    epub.write_bytes(b"PK\x03\x04epub")
    secrets = Secrets(
        kindle_email="me_abc@kindle.com",
        sender_email="me@gmail.com",
        smtp_host="smtp.gmail.com",
        smtp_user="me@gmail.com",
        smtp_password="x",
    )
    msg = build_message(epub, secrets, "Le Quotidien 2026-09-30")
    assert msg["Date"]
    assert msg["Message-ID"].endswith("@gmail.com>")
    (att,) = msg.iter_attachments()
    assert att.get_content_type() == "application/epub+zip"
    assert att.get_filename() == "issue.epub"
