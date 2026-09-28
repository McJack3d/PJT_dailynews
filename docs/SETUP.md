# Detailed setup

## 1. Create your copy

Use **Use this template → Create a new repository**. A fork would also work, but GitHub
disables Actions in forks until you enable them manually under the **Actions** tab.

## 2. Find your Kindle email address

Amazon → **Account → Manage Your Content and Devices → Preferences → Personal Document
Settings**. Each device (and the Kindle app) has a **Send-to-Kindle E-Mail** such as
`yourname_abc123@kindle.com`. Pick the device that should receive the paper.

## 3. Choose a sending account

Amazon only accepts documents from addresses you approve, and the mail must genuinely come
from that address (SPF/DKIM), so use a real mailbox you control.

**Gmail (recommended):**
1. Turn on 2-Step Verification for the Google account.
2. Create an App Password at <https://myaccount.google.com/apppasswords>.
3. Secrets: `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`, `SMTP_USER=you@gmail.com`,
   `SMTP_PASSWORD=<the 16-letter app password>`.

A dedicated Gmail account just for this is a good idea: the app password then can't
touch your main mailbox.

**Others:** Fastmail (`smtp.fastmail.com`, app password), iCloud (`smtp.mail.me.com`,
app-specific password), or the SMTP relay of Brevo, Mailgun, Resend or SendGrid (verify your
domain first, then use their SMTP host/user/key). Outlook.com and Hotmail are not supported:
Microsoft removed password-based SMTP.

## 4. Approve the sender at Amazon

Same **Personal Document Settings** page → **Approved Personal Document E-mail List** →
**Add a new approved e-mail address** → the address from step 3 (`SENDER_EMAIL`, or
`SMTP_USER` if you didn't set one).

## 5. Add the secrets

Repo → **Settings → Secrets and variables → Actions → New repository secret**. Add
`KINDLE_EMAIL`, `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, and optionally `SMTP_PORT`,
`SENDER_EMAIL`, `BCC_EMAIL`.

Until `KINDLE_EMAIL` exists the daily workflow skips itself, so an unconfigured copy never
fails.

## 6. Test

**Actions → Daily issue → Run workflow.** The run's summary lists the articles it sent. The
issue shows up on the Kindle a few minutes later (wireless must be on).

## 7. Pick your delivery time

Edit the `cron` line in `.github/workflows/daily.yml`. It is in **UTC**:
`"17 5 * * *"` is 05:17 UTC = 07:17 in Paris in summer, 06:17 in winter. Runs often start
5–30 minutes late.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Run fails with `SMTPAuthenticationError` | Wrong user/password. For Gmail, use an App Password, not your normal password. |
| Run succeeds, nothing on the Kindle | The sender isn't on Amazon's approved list, or `KINDLE_EMAIL` has a typo. Check the sender's inbox for a message from Amazon. Set `BCC_EMAIL` to confirm mails leave. |
| Amazon replies "document failed to convert" | Please open an issue with the date. As a workaround, lower `max_articles`. |
| Many articles show only a summary | Those sites block extraction or are paywalled. Add feeds from sites with full-text pages. |
| "No matching articles today" | Broaden `keywords`, raise `max_age_hours`, or add feeds. |
| Schedule stopped running | GitHub disables schedules after 60 days without commits. The state commit prevents this, but if it happened, re-enable the workflow in the Actions tab. |
