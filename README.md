# CreatorBridge: Influencer Marketing Platform

A two-sided marketplace for India. Brands share a product link and budget and get matched with nano and micro Instagram creators. The platform handles contracts, consent, payment, approvals and publishing, and creators are paid once their post has been verified live.

- Product plan: [docs/PRODUCT_PLAN.md](docs/PRODUCT_PLAN.md)
- Dashboards and analytics spec: [docs/DASHBOARDS.md](docs/DASHBOARDS.md)
- Tech stack (Python/Django, free-tier v1), APIs and task list: [docs/TECH_PLAN.md](docs/TECH_PLAN.md)

## What works today

| Area | Status |
|---|---|
| Accounts with roles (brand / creator / ops) | ✅ |
| Niche taxonomy (20 categories, 60 sub-niches) | ✅ |
| Creator onboarding: profile, Instagram connect (mock or Meta API), rates, red lines, AI preference, KYC with encrypted PAN/bank details, e-signed agreement | ✅ |
| Brand onboarding: profile, GSTIN/PAN validation (with checksum), DNS domain verification, e-signed agreement | ✅ |
| Contracts: exact text stored with SHA-256, typed-name + email OTP signing, consent ledger, consent centre with revocable consents | ✅ |
| Campaigns: product URL reading (SSRF-safe), Gemini brief extraction with rule-based fallback, sensitive-category and risky-claim flags, brief edit/confirm | ✅ |
| Matching: hard filters, weighted scoring, budget-aware selection, tier mix, backups, explanations, "not enough creators" state | ✅ |
| Pricing: brand price = creator fee ÷ (1 − margin), GST; brand pages never receive creator fees | ✅ |
| Ops: review queue, approve/reject/KYC actions in admin, audit log | ✅ |
| Offers: send to selected creators, accept via e-signed campaign agreement, decline with reason, 48h expiry, automatic backup offers within budget, "unfilled" when backups run out | ✅ |
| Payments: pay only for accepted creators, e-signed campaign order, mock or Razorpay checkout (signature-verified), idempotent webhooks with amount check, GST invoice (CGST+SGST or IGST) with gap-free numbering | ✅ |
| Payouts: held per creator with TDS (1% individual / 2% others) and GST if registered; released automatically after verification; ops marks paid with UTR | ✅ |
| Content: creator workspace with AI script helper, draft upload with automated checks (ad disclosure, forbidden phrases, risky claims, file type), brand review with 2 revision rounds and 72h auto-approval | ✅ |
| Publishing: creator's final OK on the exact file (consent stored with its SHA-256), scheduled auto-publish via Instagram API, self-post fallback with link verification | ✅ |
| Verification: daily checks for 7 days, payout on hold if the post disappears or loses its disclosure, weekly monitoring until the minimum live period ends; campaign results (reach, views, engagement rate, CPM) | ✅ |
| Dashboards: brand home (spend, reach, views, ER, CPM, views chart, upcoming posts), per-creator results and chart, printable campaign report, content library with usage-rights expiry, billing, weekly email digest | ✅ |
| Creator earnings: monthly chart, payment history with UTR, post performance, financial-year statement with quarterly TDS totals | ✅ |
| Refunds: creator withdrawal or ops cancellation before approval refunds the brand with a GST credit note (own gap-free series); unpaid stale slots refunded automatically; billing shows net spend | ✅ |
| Disputes: brand or creator reports a problem, payout held while open, ops evidence pack (agreements, consents with hashes, drafts, reviews, post checks, timeline), resolve as pay creator / full refund / split | ✅ |
| Rebooking: "Run again" copies a campaign's settings and confirmed brief, with creators who delivered picked first; "Add creators" finds more creators for a running campaign (extra budget, excludes everyone already offered), billed on a separate invoice | ✅ |
| Deployment (Oracle Cloud free tier) | Later |

## Run it locally

You need **uv** (it installs the right Python for you). Nothing else: no database server, no Redis, no Node.js.

**1. Install uv** (once)

- macOS / Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Windows (PowerShell): `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`

**2. Get the code and start it**

Windows (PowerShell):

```powershell
git clone https://github.com/arindamghosh10/Influencer-marketing-platform.git
cd Influencer-marketing-platform
git checkout claude/vigilant-hamilton-l0fhds
Copy-Item .env.example .env
uv sync
uv run python manage.py devserver
```

macOS / Linux:

```bash
git clone https://github.com/arindamghosh10/Influencer-marketing-platform.git
cd Influencer-marketing-platform
git checkout claude/vigilant-hamilton-l0fhds
cp .env.example .env
uv sync
uv run python manage.py devserver
```

After installing uv, close and reopen the terminal so the `uv` command is found.

`devserver` creates the local database (`db.sqlite3`), loads demo data the first time, starts the background scheduler (offer expiry, review auto-approval, publishing, post verification, weekly reports) and the web server.

**3. Open http://127.0.0.1:8000** and log in (password `demo-pass-123` for all):

| Account | What to try |
|---|---|
| `brand@demo.local` | New campaign → confirm brief → pick creators → send offers → pay (test mode) → review drafts → see results, content library, billing |
| `creator000@demo.local` | Offers, campaign workspace, earnings and FY statement. Or sign up as a new creator to try onboarding |
| `ops@demo.local` | `/ops/` (review queues, "Run scheduled jobs now") and `/admin/` (approve users, mark payouts paid) |

Signing codes and emails are printed in the terminal (and shown on screen in debug mode). To see offers from the brand's campaign, log in as the creator named on the campaign page; the ops admin (`/admin/` → Users) shows every creator's email.

**Tips**
- Start fresh: stop the server, delete `db.sqlite3` and the `media/` folder, run `devserver` again.
- The stylesheet is included. If you change templates, run `uv run python manage.py devserver --build-css` to rebuild it (downloads the Tailwind tool, about 145 MB, the first time).
- Use PostgreSQL instead: set `DATABASE_URL` in `.env` (see `.env.example`), or run everything with `docker compose up --build`.
- Real AI briefs: set `LLM_PROVIDER=gemini` and `GEMINI_API_KEY` in `.env` (free key from https://aistudio.google.com).

## Tests and checks

```bash
uv run pytest            # unit + end-to-end flow tests (SQLite by default; set DATABASE_URL for Postgres)
uv run ruff check . && uv run ruff format --check .
```

## Switching free services on

| Setting | Values |
|---|---|
| `LLM_PROVIDER` | `rules` (free, offline) · `gemini` (set `GEMINI_API_KEY`; free tier is rate-limited and Google may use free-tier prompts to improve its models) |
| `INSTAGRAM_PROVIDER` | `mock` (demo stats) · `graph` (Meta app with approved Instagram permissions) |
| `PAYMENTS_PROVIDER` | `mock` (test-mode button) · `razorpay` (set key id/secret and webhook secret; use Razorpay test keys first) |

Background jobs: offer expiry, unpaid-slot release, review auto-approval, scheduled publishing and post verification run every 5 minutes via Celery Beat (`celery -A config worker -B`), or manually with `python manage.py run_deadlines` or the "Run scheduled jobs now" button on the ops page.

If Gemini fails or runs out of quota, the app automatically falls back to the rule-based brief.

## Layout

```
config/            settings, URLs, Celery
apps/core          audit log, notifications, money/pricing, validators, ops page
apps/accounts      custom user with roles, signup/login
apps/niches        taxonomy + sensitive categories
apps/creators      creator profile, onboarding, Instagram sync, authenticity score
apps/brands        brand profile, onboarding, domain verification
apps/contracts     agreements, OTP signing, consent ledger
apps/campaigns     campaigns, product briefs
apps/matching      matching engine (pure Python) + persistence
apps/offers        slots, offers, backups, deadlines job
apps/payments      orders, Razorpay/mock checkout, webhooks, GST invoices, payouts with TDS
apps/content       drafts, reviews, final approval, publishing, verification, metrics
apps/integrations  adapters: Instagram (mock/graph), LLM (rules/Gemini), SSRF-safe fetch
tests/             pytest suite
```
