# dailynews: plan and feasibility audit

**Goal:** an open-source repo that, every day and with no human action, builds a personal newspaper from the reader's interests and delivers it to their Kindle through Amazon's **Send to Kindle** email service.

**Decisions so far:**
- **Content mode: hybrid.** Real articles come from RSS and news sources. An optional LLM step ranks them against the reader's interests and writes a short front-page briefing. The pipeline still works with no API key; it then filters by keyword.
- **Runtime: GitHub Actions cron.** Users click "Use this template", add a few secrets, edit one config file, and they are done. Nothing to host.

---

## 1. Feasibility audit

**Verdict: feasible, and already proven by prior art.** The parts that can go wrong are delivery (email and sender setup) and scheduling reliability. Content generation is the easy part.

### 1.1 Delivery via Send to Kindle email: ✅ feasible, with conditions

| Fact | Consequence for the design |
|---|---|
| Each Kindle account has an address `name@kindle.com`. Amazon only accepts mail from senders on the account's **Approved Personal Document E-mail List**. | This is a one-time manual step per user, done in the Amazon account. After that, delivery needs no human action. |
| **EPUB** is the recommended format. MOBI has not been accepted since 2022. PDF, DOCX, HTML and TXT also work. | Generate EPUB. It reflows, keeps a table of contents, and Amazon converts it to KF8/AZW3 on its side. |
| The limit is about 50 MB per email and 25 attachments. | A text-only daily issue is under 1 MB. With compressed images it is still well under 10 MB. |
| Amazon's EPUB converter is strict. A malformed EPUB triggers a "document failed to convert" email. | Build EPUB3 with valid XHTML, set `dc:language`, use only JPEG/PNG images, include a nav doc, and **run `epubcheck` in CI**. |
| The Send to Kindle email service has no official API. | Email (SMTP) is the only automatable path. The browser upload, apps and USB options all need a person. |
| Amazon checks the `From:` address, and mail must pass SPF and DKIM for it. | Send through a real mailbox or a domain you control. Never spoof the `From:` address. |

**Sending options, in the order the docs will recommend them:**
1. **Gmail SMTP with an App Password.** Free. Needs 2-Step Verification on the Google account. Tested path, and Calibre users have relied on it for years. *Risk:* Google keeps restricting password-based SMTP. App Passwords still work for personal accounts, but this should be re-checked at launch.
2. **Transactional email API** (Resend, Brevo, Mailgun, SendGrid). Free tiers are far above one email a day. Needs a verified sender domain, which is more setup but the most robust against policy changes. Supported through a small provider interface.
3. **Any generic SMTP server** (Fastmail, iCloud, a self-hosted server) using host, port, user and password.
4. ⚠️ **Outlook.com / Hotmail.** Microsoft has removed basic-auth SMTP for consumer accounts. Document it as unsupported.

**Failure visibility:** Amazon's failure notices go to the sender's inbox, which nobody reads in an automated setup. Mitigations:
- Validate the EPUB before sending (`epubcheck`).
- Mark the GitHub Actions job as failed if SMTP rejects the message, so GitHub emails the repo owner.
- Optionally, also send a copy to the user's own address (`BCC_SELF`).

### 1.2 Content sourcing: ✅ feasible

- **RSS/Atom feeds** are free, stable, and legal to fetch. Most major outlets and blogs still publish them.
- **Full-text extraction** (`trafilatura`) turns a partial feed item into a readable article. It fails on paywalled sites, so those items fall back to the RSS summary plus a link.
- **Discovery by interest,** for people who don't want to curate feeds:
  - Google News RSS search: `https://news.google.com/rss/search?q=<topic>` gives one feed per interest.
  - Hacker News and Reddit RSS.
  - Optionally, a GDELT or NewsAPI key.
- **Deduplication** by URL and by fuzzy title match, so one story isn't included five times.

### 1.3 Interest matching and briefing with an LLM: ✅ feasible and cheap

- **One API call per day.** The input is about 60 to 150 candidate headlines with snippets (roughly 10–20k tokens). The output is a ranking plus a briefing of about 500–800 words, returned as structured JSON (`output_config.format`).
- **Web search is not needed** in hybrid mode because the feeds already supply the sources. The briefing may only cite articles in the issue, which keeps it grounded and makes every claim traceable to a link.
- **Default model:** `claude-opus-5` ($5 / $25 per million input/output tokens). A day costs about 15k input and 3k output tokens, so **≈ $0.15/day, or ≈ $4.50/month**. The model is configurable: `claude-sonnet-5` costs about 2.5× less and `claude-haiku-4-5` about 5× less.
- **Without an API key,** ranking falls back to keyword and TF-IDF scoring against the interests, and the briefing is replaced by a plain table of contents.
- The LLM layer is behind a small interface so other providers can be added by contributors.

### 1.4 Scheduling on GitHub Actions: ⚠️ feasible with known caveats

| Caveat | Mitigation |
|---|---|
| Scheduled runs are delayed, often by 5–30 minutes and sometimes more under load. | Schedule about an hour before the reader wants the issue. Use an off-peak minute (for example `17 5 * * *`, not `0 5 * * *`). |
| **Scheduled workflows are disabled automatically after 60 days without repository activity** on public repos. This is the biggest risk to "no human interference". | Each run commits a small state file (`state/seen.json`, used for dedup) back to the repo. That counts as activity and keeps the schedule alive. |
| Forked repos have Actions disabled by default. | Tell users to use **"Use this template"** instead of forking. The README includes a one-click setup checklist. |
| Cron is in UTC. | The config accepts a timezone and delivery hour; a helper prints the matching cron line. DST shifts the delivery by an hour unless the workflow checks the local time itself. The simpler option is accepted. |
| Minutes are free and unlimited on public repos. Private repos get 2,000 minutes a month. | A run takes about 1–2 minutes, so both are fine. |

Secrets such as the Kindle address, SMTP credentials and API key live in **GitHub Actions secrets**, never in the committed config, because the user's copy of the repo is usually public.

### 1.5 Legal and ethical: ⚠️ document it, don't ignore it

- The tool fetches full article text **for the user's personal reading**, which is the same model as Calibre's "Fetch news" or a read-it-later app. The repo ships code, not content. It must never publish generated issues publicly: no committing EPUBs and no GitHub Pages. That means the workflow keeps the EPUB out of the repo and only keeps it as a short-lived, private Actions artifact.
- Respect `robots.txt` and send a descriptive User-Agent.
- Don't include paywall-bypass logic.
- Only the **commit of `state/seen.json`** is public, and it contains only URL hashes, which reveal nothing about the user.
- LLM briefings must attribute and link their sources.
- License: **MIT**.

### 1.6 Prior art (reuse ideas, avoid reinventing)

- **Calibre** (`ebook-convert` plus news "recipes") has a robust HTML-to-EPUB pipeline and hundreds of existing site recipes. It is too heavy as a dependency (a 200 MB+ install). Consider it as an optional backend.
- **KindleEar** is an open-source RSS-to-Kindle project that runs on its own server. It confirms the email approach works long term, but it needs hosting.
- **Send-to-Kindle bots and Pocket/Instapaper-to-Kindle tools** show that the approved-sender flow is reliable once set up.

What this project adds: **zero hosting (a GitHub template), interest-based curation, and an AI front page.**

---

## 2. Architecture

```
config.yaml (interests, feeds, schedule, options)
        │
        ▼
┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│   collect    │──▶│   extract    │──▶│  rank/brief  │──▶│  build EPUB  │──▶│   deliver    │
│ RSS, Google  │   │ trafilatura, │   │ LLM or TF-IDF│   │ ebooklib,    │   │ SMTP/API to  │
│ News, HN…    │   │ images, dedup│   │ + briefing   │   │ epubcheck    │   │ @kindle.com  │
└──────────────┘   └──────────────┘   └──────────────┘   └──────────────┘   └──────────────┘
        ▲                                                                          │
        └───────────────── state/seen.json (dedup, committed daily) ◀──────────────┘
```

**Stack:** Python 3.12, `feedparser`, `httpx`, `trafilatura`, `ebooklib`, `Pillow`, `anthropic` (optional extra), `pydantic` (for config), and `smtplib` from the standard library. The package manager is `uv`.

### Repo layout

```
dailynews/
├── .github/workflows/
│   ├── daily.yml            # cron: build + send, commit state
│   └── ci.yml               # lint, tests, epubcheck on a fixture issue
├── dailynews/
│   ├── __main__.py          # `python -m dailynews run|preview|test-email`
│   ├── config.py            # pydantic schema for config.yaml + env secrets
│   ├── sources/             # rss.py, google_news.py, hackernews.py (plugin registry)
│   ├── extract.py           # full text, cleaning, image fetch/resize, dedup
│   ├── rank/
│   │   ├── keyword.py       # no-API fallback (TF-IDF vs interests)
│   │   └── llm.py           # Claude: rank + briefing, structured output
│   ├── epub/
│   │   ├── builder.py       # EPUB3: cover, briefing, sections per interest, nav
│   │   ├── cover.py         # generated cover with date + headlines (Pillow)
│   │   └── templates/       # XHTML + CSS tuned for e-ink
│   ├── deliver/
│   │   ├── smtp.py
│   │   └── resend.py        # example API provider
│   └── state.py             # seen-URL store (hashed)
├── config.example.yaml
├── state/seen.json
├── tests/                   # fixtures: canned feeds/HTML → golden EPUB structure
├── docs/SETUP.md            # step-by-step with screenshots (approved sender!)
├── LICENSE (MIT)
└── README.md
```

### Example `config.yaml`

```yaml
title: "My Daily Brief"
language: en
timezone: Europe/Paris
deliver_at: "07:00"
max_articles: 25
interests:
  - name: AI research
    keywords: [LLM, "machine learning", Anthropic, OpenAI]
  - name: Formula 1
    keywords: [F1, "Formula 1"]
  - name: French politics
    google_news: "politique France"   # auto-discovered feed
feeds:                                # optional hand-picked feeds
  - https://hnrss.org/frontpage
  - https://www.theverge.com/rss/index.xml
llm:
  enabled: true
  model: claude-opus-5
  briefing_words: 600
images: true
```

**Secrets:** `KINDLE_EMAIL`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SENDER_EMAIL`, and optionally `ANTHROPIC_API_KEY`.

---

## 3. Delivery milestones

1. **MVP (end-to-end, no LLM).** Build `config.py`, the RSS source, extraction, the keyword ranker, the EPUB builder and SMTP delivery, plus `daily.yml`. *Done when:* a scheduled run lands an issue on a real Kindle.
2. **Hardening.** Add `epubcheck` in CI, retries and timeouts, per-source failure isolation (one dead feed can't kill the issue), the dedup state commit (which also serves as the keepalive), a `preview` command that writes the EPUB locally, and `test-email`.
3. **Interests and LLM.** Add Google News discovery per interest, LLM ranking and the briefing with structured output, and the fallback path when the API errors.
4. **Polish for open source.** Generated cover, e-ink CSS, image compression, `docs/SETUP.md` with the Amazon approved-sender walkthrough, a template-repo flag, issue templates, a CONTRIBUTING guide, and a source plugin guide.
5. **Optional extras.** A Docker image for self-hosters, weekly digest mode, multiple recipients (family Kindles), and a Calibre backend.

## 4. Verification

- **Unit tests** with canned feeds and HTML fixtures. The golden test checks EPUB structure: chapters, nav and metadata.
- **`epubcheck`** runs in CI on the fixture issue, and the build fails on any error.
- **`python -m dailynews preview`** writes `out/issue.epub` for manual inspection in Calibre or the Kindle Previewer.
- **`python -m dailynews test-email`** sends a one-page EPUB to confirm that the approved-sender setup works.
- **A real end-to-end run:** a `workflow_dispatch` run from the Actions tab delivers to the maintainer's Kindle. Then leave the cron running for more than 7 days and confirm daily delivery and the timing drift.

## 5. Risks that stay open

| Risk | Likelihood | Impact | Note |
|---|---|---|---|
| Google tightens App Password SMTP | Medium | High for Gmail users | The API-provider path exists as a fallback. |
| Amazon changes Send to Kindle email (formats, verification) | Low–Medium | High | This is the only automatable channel. Monitor it and keep the delivery layer pluggable. |
| GitHub Actions cron delays or disables the schedule | Low (with keepalive) | Medium | The state commit keeps it active, and a job failure notifies the owner. |
| Sites block extraction | High for some sites | Low | Fall back to the RSS summary plus a link. |
| LLM cost surprises | Low | Low | One call per day, `max_tokens` capped, cost logged in the job summary. |
