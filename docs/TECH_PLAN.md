# Tech Plan: Stack, APIs and Tasks (v1, Python, free tier)

> Companion to [PRODUCT_PLAN.md](PRODUCT_PLAN.md) and [DASHBOARDS.md](DASHBOARDS.md).
>
> Decisions this is based on: India first · all major niches · AI as a speed/cost helper (creator-made content is the default) · paid-ads usage rights from day 1 · 50/50 split, not disclosed (platform as principal) · nano and micro creators · **Python** · **free tiers and open-source for v1, upgraded to the best paid services later.**

---

## 1. Guiding rule: free now, swappable later

Every external service sits behind an **adapter**: a small Python class with one interface and several implementations (`mock`, `free`, `paid`). Which one runs is chosen by an environment variable. Upgrading from, say, manual payouts to RazorpayX later is a new adapter plus a config change, not a rewrite.

```python
# example: settings pick the implementation
PAYOUT_PROVIDER = "manual"        # v1: ops pays by bank/UPI, records UTR
# PAYOUT_PROVIDER = "razorpayx"   # later
```

v1 running cost: **about ₹0/month** plus a domain (~₹800/year). The unavoidable costs are per-transaction payment fees, and AI usage if you choose a paid model (§3.1).

---

## 2. Tech stack (Python)

| Layer | v1 choice (free) | Why |
|---|---|---|
| Language | **Python 3.12** | Your choice; best ecosystem for AI, data and matching |
| Web framework | **Django 5.2 (LTS)** | Batteries included: auth, ORM, migrations, forms, security. **Django Admin gives the ops console almost for free** |
| Frontend | **Django templates + HTMX + Alpine.js + Tailwind CSS** (Tailwind standalone CLI, no Node needed) | Interactive pages written in Python/HTML, with no separate JavaScript app to build and maintain. Works well on phones for creators |
| Charts | **Chart.js** | Free, simple, good-looking dashboards |
| JSON API (for a future mobile app, webhooks) | **Django Ninja** | Fast, typed API with auto-generated docs |
| Auth | **django-allauth**: email + password, email OTP / magic link, **Google login** | All free. Phone SMS OTP costs money in India (DLT), so it comes later |
| Database | **PostgreSQL 16 + pgvector** | Reliable for money and contracts; pgvector stores AI embeddings for matching |
| Background jobs and timers | **Celery + Celery Beat + Redis** | Deadlines (48h offer expiry, 7-day verification, payouts) are **stored in the database** and a scheduled job processes them every few minutes, so nothing is lost on restart |
| File storage | **Cloudflare R2** (10 GB free, no download fees; S3-compatible) | Videos, images, signed contracts |
| Video processing | **FFmpeg** | Convert to Instagram specs, thumbnails, subtitles |
| PDF generation (contracts, invoices, reports) | **WeasyPrint** | HTML → PDF, free |
| Tooling | **uv** (packages), **Ruff** (lint/format), **pytest** + pytest-django, **Playwright for Python** (end-to-end tests) | Fast, standard, free |
| Local and server setup | **Docker Compose** (web, worker, scheduler, Postgres, Redis) | Same setup on your laptop and on the server |

### Hosting (free)
| Option | What you get | Catch |
|---|---|---|
| **Oracle Cloud Always Free** (recommended) | An ARM VM with up to 4 CPUs / 24 GB RAM, in the Mumbai or Hyderabad region. Runs the whole Docker Compose stack incl. Postgres and Redis; **Caddy** gives free HTTPS | You manage the server yourself (I'll script it); sign-up needs a card for verification |
| Render (free web service) + **Supabase** free Postgres (Mumbai region) + **Upstash** free Redis | Zero server management | Free web service sleeps after inactivity (slow first load); Supabase free projects pause after a week without activity; background workers aren't free on Render |

### Monitoring and ops (free tiers)
| Need | Free service |
|---|---|
| Error alerts | **Sentry** (free developer plan) |
| Product analytics, funnels, feature flags | **PostHog** (free up to 1M events/month) |
| Uptime alerts | **UptimeRobot** or Better Stack free |
| CI (tests on every change) | **GitHub Actions** (2,000 free minutes/month for private repos) |
| DNS, SSL, basic DDoS protection | **Cloudflare** free |

---

## 3. APIs and services: v1 (free) → later (best)

### 3.1 AI

| Need | v1 (free) | Later (best) |
|---|---|---|
| Understand product from URL/images, write scripts/hooks/captions, compliance checks, match explanations | **Choose one** (see note below) | **Claude API** (`claude-opus-5`) |
| Content similarity for matching (embeddings) | **sentence-transformers**, run on our own server (`intfloat/multilingual-e5-small`, which handles Hindi and English) | Voyage AI embeddings (text + images) |
| Speech-to-text of Reels (niche detection) | **faster-whisper** running on our server (small model, CPU) | Sarvam AI (best for Indian languages and Hinglish) |
| Comment sentiment | Same LLM as above in daily batches, or a free open-source sentiment model | Claude Message Batches API |
| AI video/avatars (Phase 2) | Not in v1 | HeyGen / Veo / Runway, ElevenLabs voice |

**Note on the LLM (the one place "free" has real trade-offs):**
- **Rule-based only (₹0):** the product page is read from its structured data (schema.org, OpenGraph, Shopify JSON). Niches are mapped by keywords. Scripts come from templates. It works, but it is noticeably less smart.
- **Free-tier LLM APIs** (e.g. Google Gemini or Groq free tiers): ₹0 but rate-limited. Some free tiers may use your data to improve their models, which is a concern for brand data. Check the terms before using.
- **Claude API (paid, pay-as-you-go):** no free tier, but v1 volume is small. One brief extraction is a few thousand tokens, so a few rupees per campaign, and a $5 credit covers a lot of testing. Best quality.

I'll build an `LLMProvider` adapter with the **rule-based version always available as a fallback**, so the app never breaks if the AI is down or out of quota.

### 3.2 Instagram / Meta (free)
| Need | API | Notes |
|---|---|---|
| Creator login, profile, media, audience demographics, insights | **Instagram API with Instagram Login** (free) | Creator/Business accounts only. Long-lived tokens (~60 days), auto-refreshed |
| Publishing Reels/posts | Content Publishing API (free) | Daily per-account cap. Video must be at a public URL (R2 signed link) |
| Verification and metrics | Media + insights endpoints; webhooks (free) | Daily during the 7 days, weekly until the minimum live period ends |
| Paid-ads reuse (whitelisting) | Creator grants partner access in the Instagram app; we track it | Marketing API automation later |
| Requirement | **Meta Business Verification + App Review** (free, slow) | Start immediately. Until approved, it works only with test accounts added to the app |

Creator authenticity in v1: **our own scoring** (engagement vs. followers, follower-growth jumps, comment quality) plus manual ops review. Later: Modash / HypeAuditor / Phyllo.

### 3.3 Money
| Need | v1 | Later |
|---|---|---|
| Brand payments (UPI, cards, netbanking) | **Razorpay Payment Gateway**: no setup or annual fee, pay only per transaction (~2%); test mode is free for development | Same (or Cashfree/Juspay for better rates at volume) |
| Creator payouts | **Manual by ops**: the system calculates the fee, TDS and net amount and shows a payout list. Ops pays by bank/UPI and enters the UTR, and the creator sees it immediately | RazorpayX Payouts (automatic) |
| Bank account check | Creator uploads cancelled cheque/passbook; ops verifies; first payout ₹1 test if needed | Automatic penny-drop validation |
| GST invoices, TDS statements | **Generated in-house** (WeasyPrint PDFs) + CSV export for your CA | Zoho Books / Tally integration, e-invoicing via GSP when turnover requires it |

### 3.4 Identity, contracts, communication
| Need | v1 (free) | Later |
|---|---|---|
| KYC (PAN, GSTIN, bank) | PAN/GSTIN **format and checksum validation** + document upload + **manual ops review** | Cashfree Secure ID / Signzy (automatic verification, DigiLocker) |
| Contracts and e-sign | **In-house clickwrap e-contract**: full contract shown, typed full name + checkbox + **email OTP**. Signed PDF generated with a SHA-256 hash, time, IP and device stored (valid electronic contract under India's IT Act for normal commercial agreements; confirm with your lawyer) | Leegality / Digio with Aadhaar eSign for high-value deals |
| Notifications | **In-app** + **email** (Brevo free: 300/day, or Gmail SMTP for testing) + **browser push** (free, `pywebpush`) | WhatsApp Business (Cloud API directly from Meta: no middleman fee; you pay per message template) + SMS via MSG91 |
| Login OTP | Email OTP / magic link | Phone OTP via SMS/WhatsApp |

### 3.5 Brand integrations and utilities (free)
| Need | Tool |
|---|---|
| Read product pages | **httpx + BeautifulSoup + extruct** (reads schema.org/OpenGraph/JSON-LD), **Playwright** for JavaScript-heavy pages; SSRF protection (never fetch internal addresses) |
| Sales attribution | **Shopify Admin API** + order webhooks (free; uses the brand's store), per-creator discount codes |
| Link tracking | Own short-link service with UTM tags |
| Music for Reels | Free libraries with commercial licences (e.g. YouTube Audio Library, Pixabay Music; check each track's licence) |

---

## 4. Upgrade path summary

| Area | v1 (free) | Upgrade when… | To |
|---|---|---|---|
| Hosting | Oracle Always Free VM | Traffic grows or you want managed infra | AWS Mumbai (ECS + RDS) |
| LLM | Rule-based / free tier / small Claude credit | Quality matters for paying brands | Claude API |
| Embeddings | sentence-transformers (self-hosted) | Matching quality plateaus | Voyage AI |
| Transcription | faster-whisper | Hinglish accuracy issues | Sarvam AI |
| Payouts | Manual + UTR entry | More than ~50 payouts/week | RazorpayX Payouts |
| KYC | Manual review | More than ~20 signups/day | Cashfree Secure ID |
| E-sign | In-house clickwrap + email OTP | Enterprise brands ask for it | Leegality / Digio |
| Notifications | Email + push + in-app | Creators miss offers | WhatsApp Cloud API |
| Authenticity data | Own heuristics | Fraud appears | Modash / HypeAuditor |
| Storage | Cloudflare R2 free 10 GB | Over 10 GB | R2 paid (cheap) or S3 |

---

## 5. Task list (MVP)

About 12 weeks of build. Each epic ends with working, tested software.

### Epic 0: Foundations (week 1)
- [ ] Django project, uv, Ruff, pytest, GitHub Actions CI, Docker Compose (web, worker, beat, Postgres + pgvector, Redis)
- [ ] Apps/modules: `accounts`, `brands`, `creators`, `niches`, `campaigns`, `matching`, `contracts`, `payments`, `content`, `publishing`, `notifications`, `dashboards`, `integrations`
- [ ] Auth (django-allauth: email, OTP, Google), roles (brand / creator / ops)
- [ ] Base UI (Tailwind + HTMX), three layouts (brand, creator, ops)
- [ ] Adapter framework + mock implementations for every external service
- [ ] Event/audit log; settings for feature flags

### Epic 1: Niche taxonomy and onboarding (weeks 2-3)
- [ ] Niche taxonomy: 15+ categories with sub-niches (beauty, skincare, fashion, fitness, food, travel, tech, gaming, parenting, finance, education, lifestyle, home decor, health/wellness, pets, automotive, comedy/entertainment, sports, regional/language)
- [ ] Creator onboarding: Instagram connect, stats/audience sync, suggested niches, rate card, red lines, AI preferences, KYC documents, agreement signing
- [ ] Brand onboarding: domain verification (DNS TXT / email on domain), GSTIN/PAN, profile, restricted-category check, agreement signing
- [ ] Ops review queues (Django Admin)

### Epic 2: Creator data pipeline (weeks 3-4)
- [ ] Daily Celery sync of media, insights, audience
- [ ] Transcripts (faster-whisper), embeddings (sentence-transformers → pgvector)
- [ ] Authenticity score (own heuristics), brand-safety keyword scan
- [ ] Token refresh and "reconnect Instagram" flow

### Epic 3: Campaign creation and product understanding (week 4)
- [ ] Campaign form (objective, budget, deliverables, audience, timeline, must-say/must-not-say, usage rights incl. paid ads)
- [ ] Product URL reader (structured data first, SSRF-safe) + image upload
- [ ] Brief extraction via `LLMProvider` (rule-based fallback always on), niche mapping, restricted-category and risky-claim flags
- [ ] Brief review and confirm (versioned)

### Epic 4: Matching engine (weeks 5-6)
- [ ] Hard filters (niche, geo, gender/age, budget, content mode, red lines, competitor conflicts, capacity, authenticity, account health)
- [ ] Weighted scoring (audience fit, content similarity, performance, reliability, price efficiency, saturation)
- [ ] Budget optimiser (best set within budget, tier mix), backups per slot, "not enough creators" state
- [ ] Plain-language explanations; unit tests on synthetic creators

### Epic 5: Pricing, contracts and consent (week 6)
- [ ] Margin engine: brand price = creator fee ÷ (1 − margin); 50% default, global and per-campaign
- [ ] Strict separation: brand views never contain creator fee and creator views never contain brand price, enforced in one place and covered by tests
- [ ] Contract templates (brand order; creator agreement incl. paid-ads usage rights, minimum live period, non-circumvention) → PDF + hash
- [ ] Clickwrap + email-OTP signing; consent ledger

### Epic 6: Offers and workflow engine (weeks 7-8)
- [ ] Campaign/slot state machine (PRODUCT_PLAN §6) with database-stored deadlines + Celery Beat processor
- [ ] Offers with 48h expiry → automatic backup offers; reminders; replacement and refund rules
- [ ] Notifications: in-app, email, browser push

### Epic 7: Payments and payouts (week 8)
- [ ] Razorpay checkout + verified webhooks; GST invoice PDFs
- [ ] Internal ledger (held → released → paid); refunds
- [ ] Payout queue for ops (fee, TDS, net) with UTR entry; creator earnings statements

### Epic 8: Content production and approvals (weeks 9-10)
- [ ] AI/template creator brief (script, hooks, shot list, caption)
- [ ] Draft upload direct to R2; FFmpeg processing to Instagram specs
- [ ] Automated checks (disclosure present, banned claims, must-say points)
- [ ] Brand review (2 revisions, 72h auto-approve); creator final approval with asset hash

### Epic 9: Publishing and verification (week 10)
- [ ] Scheduled publishing via Instagram API; self-post fallback with link verification
- [ ] Partnership-ads access tracking and reminders
- [ ] Daily verification for 7 days, weekly until minimum live period; hold/clawback
- [ ] Metrics sync

### Epic 10: Dashboards and reports (weeks 11-12)
- [ ] Brand: home, campaign detail, content library with usage-rights expiry, billing, PDF report
- [ ] Creator: home, offers, workspace, earnings, consent centre
- [ ] Ops: funnel, stuck queue, disputes, payout queue, integration health

### Epic 11: Hardening and launch (week 12)
- [ ] Security review (auth, uploads, SSRF, rate limits, encryption of PAN/bank fields)
- [ ] End-to-end tests of the full campaign lifecycle
- [ ] Backups (daily `pg_dump` to R2) and a restore drill
- [ ] Legal pages in the app (terms, DPDP privacy notice, agreements)

### Your tasks (start in week 1: long lead times, mostly free)
| Task | Cost | Lead time |
|---|---|---|
| Company registration, current accounts (operations + creator payables), GST registration | Registration fees | 2-4 weeks |
| **Meta developer app + Business Verification + App Review** | Free | 2-6 weeks |
| Razorpay account activation | Free (per-transaction fees only) | 1-2 weeks |
| Oracle Cloud (or Render/Supabase), Cloudflare, Sentry, PostHog, Brevo accounts | Free | Same day |
| Domain name | ~₹800/year | Same day |
| Lawyer review of agreements, terms and privacy notice; CA advice on GST/TDS | Professional fees | 2-4 weeks |
| Recruit 200-500 nano/micro creators across niches | Your time | Ongoing |
| Decide on LLM option (§3.1) | ₹0 to a few hundred ₹/month | Before Epic 3 |

---

## 6. How I'll build it

- Everything runs locally with **mock adapters**, so the whole flow (onboarding → matching → contracts → payment → approval → publishing → verification → payout → dashboards) works end to end on demo data from the start.
- Real free services get switched on as your accounts become ready. Keys live in environment variables and are never committed.
- Each epic lands as reviewed, tested commits.
