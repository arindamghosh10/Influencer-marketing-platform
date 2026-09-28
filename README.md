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
| Payouts: held per creator with TDS (1% individual / 2% others) and GST if registered; ops marks paid with UTR | ✅ (release after verification comes with publishing) |
| Content approvals, publishing, 7-day verification | Next |

## Run it locally

Requirements: Python 3.12, [uv](https://docs.astral.sh/uv/), PostgreSQL 16, Redis (only needed for background jobs).

```bash
cp .env.example .env                 # set DEBUG=true for local use
createuser app -P && createdb influencer -O app   # or use docker compose (below)
uv sync
uv run python manage.py migrate      # also loads the niche taxonomy
uv run python manage.py seed_demo    # demo brand, ops user and 80 creators
uv run python manage.py tailwind build
uv run python manage.py runserver
```

Open http://127.0.0.1:8000 and log in with one of the demo accounts (password `demo-pass-123`):

- `brand@demo.local`: create a campaign, confirm the brief, pick creators
- `creator000@demo.local`: an approved creator
- `ops@demo.local`: ops overview at `/ops/`, admin at `/admin/`

Or sign up as a new creator to walk through onboarding. In `DEBUG` mode the signing code is shown on screen and printed in the server log.

With Docker: `cp .env.example .env && docker compose up --build`.

## Tests and checks

```bash
uv run pytest            # unit + end-to-end flow tests (needs Postgres)
uv run ruff check . && uv run ruff format --check .
```

## Switching free services on

| Setting | Values |
|---|---|
| `LLM_PROVIDER` | `rules` (free, offline) · `gemini` (set `GEMINI_API_KEY`; free tier is rate-limited and Google may use free-tier prompts to improve its models) |
| `INSTAGRAM_PROVIDER` | `mock` (demo stats) · `graph` (Meta app with approved Instagram permissions) |
| `PAYMENTS_PROVIDER` | `mock` (test-mode button) · `razorpay` (set key id/secret and webhook secret; use Razorpay test keys first) |

Background jobs: offer expiry and unpaid-slot release run every 5 minutes via Celery Beat (`celery -A config worker -B`), or manually with `python manage.py run_deadlines` or the "Run scheduled jobs now" button on the ops page.

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
apps/integrations  adapters: Instagram (mock/graph), LLM (rules/Gemini), SSRF-safe fetch
tests/             pytest suite
```
