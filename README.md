# dailynews

A personal newspaper built from **your interests**, delivered to **your Kindle** every
morning. It runs free on GitHub Actions: no server, no app, no daily action from you.

Every day it:

1. collects recent articles from a news search per interest plus any RSS feeds you add,
2. drops anything already sent, deduplicates the same story across outlets,
3. matches articles to your interests and picks the best ones per section,
4. extracts the full text (respecting `robots.txt`; paywalled pieces fall back to summary + link),
5. builds a clean EPUB with a clickable front page, and
6. emails it to your `@kindle.com` address via Amazon's **Send to Kindle**.

## Setup (about 10 minutes, once)

1. Click **Use this template → Create a new repository** (don't fork: forks start with
   Actions disabled). Public repos get unlimited free Actions minutes.
2. Edit `config.yaml` in your new repo: your interests, optional feeds, language.
3. Create an email login that can send mail (a Gmail
   [App Password](https://myaccount.google.com/apppasswords) is easiest).
4. In Amazon's **Manage Your Content and Devices → Preferences → Personal Document
   Settings**, add that sender address to the **Approved Personal Document E-mail List**, and
   note your Kindle's `…@kindle.com` address.
5. In your repo: **Settings → Secrets and variables → Actions**, add the secrets below.
6. **Actions → Daily issue → Run workflow** to test. Your issue lands on the Kindle within a
   few minutes. After that it arrives daily at the time in `.github/workflows/daily.yml`.

Step-by-step details and troubleshooting: [docs/SETUP.md](docs/SETUP.md).

| Secret | Example | Required |
|---|---|---|
| `KINDLE_EMAIL` | `yourname_abc123@kindle.com` | yes |
| `SMTP_HOST` | `smtp.gmail.com` | yes |
| `SMTP_PORT` | `587` (STARTTLS) or `465` (SSL) | no, default 587 |
| `SMTP_USER` | `you@gmail.com` | yes |
| `SMTP_PASSWORD` | Gmail App Password (16 letters) | yes |
| `SENDER_EMAIL` | `you@gmail.com` (must be on Amazon's approved list) | no, defaults to `SMTP_USER` |
| `BCC_EMAIL` | your own inbox, to get a copy of each issue | no |

## Run locally

```bash
pip install -e ".[dev]"
python -m dailynews preview          # builds out/dailynews-YYYY-MM-DD.epub, sends nothing
export KINDLE_EMAIL=… SMTP_HOST=… SMTP_USER=… SMTP_PASSWORD=…
python -m dailynews test-email       # one-page test issue to check delivery
python -m dailynews run              # build + send + remember what was sent
pytest                               # tests (set EPUBCHECK_JAR to also validate the EPUB)
```

## Good to know

- **Delivery time:** GitHub cron is in UTC and often starts 5–30 minutes late. Schedule
  about an hour before you read.
- **Keeps itself alive:** GitHub disables schedules after 60 days without repo activity.
  Each run commits `state/seen.json` (hashes of sent URLs, used to avoid repeats), which
  counts as activity.
- **Privacy:** your Kindle address and passwords live only in encrypted secrets and are
  masked in logs. The issue is never committed or uploaded, since artifacts on public
  repos are downloadable by anyone.
- **Content:** articles are fetched for your personal reading, like Calibre's *Fetch news*
  or a read-later app. Don't republish issues. There is no paywall bypass.
- **Outlook/Hotmail** no longer allow password SMTP logins; use Gmail, Fastmail, iCloud or
  a transactional email provider's SMTP.

## Roadmap

See [PLAN.md](PLAN.md). Next: an optional AI front-page briefing and smarter ranking,
and images.

## License

MIT
