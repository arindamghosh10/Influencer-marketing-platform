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
| Offers, payments, content approvals, publishing, verification, payouts | Next |

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
apps/integrations  adapters: Instagram (mock/graph), LLM (rules/Gemini), SSRF-safe fetch
tests/             pytest suite
```
