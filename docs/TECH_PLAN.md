# Tech Plan: Stack, APIs and Tasks

> Companion to [PRODUCT_PLAN.md](PRODUCT_PLAN.md) and [DASHBOARDS.md](DASHBOARDS.md). This covers what we build with, which third-party APIs we use and why, and the full task list for the MVP, in order.
>
> Decisions this is based on: India first · all major niches · AI as a speed/cost helper (creator-made content is the default) · paid-ads usage rights from day 1 · 50/50 split, not disclosed (platform as principal) · nano and micro creators.

---

## 1. Tech stack

**One TypeScript codebase for everything** (web app, API, background workers). With a small team, and with Claude doing the building, one language and one repo is the fastest way to move and the easiest to maintain.

| Layer | Choice | Why |
|---|---|---|
| Web app (brand, creator, ops) | **Next.js (React) + TypeScript** | One framework for pages and API. Server rendering keeps dashboards fast. Very large ecosystem |
| UI | **Tailwind CSS + shadcn/ui** components; **Recharts** for charts | Clean, consistent UI quickly; easy to make mobile-friendly for creators |
| Creator mobile app | **PWA first** (installable web app); React Native (Expo) in Phase 3 | Creators get a phone-friendly app on day 1 without waiting for app-store builds |
| Database | **PostgreSQL** + **pgvector** extension | Reliable for money and contracts (transactions); pgvector stores AI embeddings for matching, so no separate vector DB |
| ORM | **Prisma** | Type-safe queries, migrations |
| Background jobs and long waits | **Inngest** (or Temporal later at larger scale) | Durable workflows: "wait 48h for creator, then offer backup", "check post daily for 7 days, then pay". Survives restarts and deploys |
| Cache / rate limits | **Redis** (Upstash) | Rate-limit Instagram API calls, OTP throttling, caching dashboard queries |
| File storage | **AWS S3 (Mumbai region)** + CloudFront CDN | Videos, images, signed contracts (Object Lock so contracts can't be altered) |
| Video processing | **FFmpeg** in the worker (transcode to Instagram specs, burn subtitles, thumbnails) | Free, standard; managed services later if volume grows |
| Hosting | **AWS ap-south-1 (Mumbai)**: ECS Fargate for app and workers, RDS Postgres. Alternative for speed: Vercel (web) + RDS Mumbai | Data stays in India (good for DPDP and payment data); low latency for Indian users |
| Auth | **Auth.js** with email + **phone OTP** | Indian users expect phone login; roles: brand, creator, ops |
| Product analytics, feature flags | **PostHog** | Funnels, session replay, flags to roll out AI features gradually |
| Errors and monitoring | **Sentry** + CloudWatch / Better Stack | Know about failures before users report them |
| CI/CD | **GitHub Actions** | Tests, type checks and lint on every PR; auto-deploy |
| Testing | **Vitest** (unit), **Playwright** (end-to-end) | Money and state-machine logic must be tested |

### Architecture at a glance
```
 Brand web ─┐                     ┌─► PostgreSQL + pgvector (RDS Mumbai)
 Creator PWA ├─► Next.js app/API ─┼─► S3 (videos, contracts)
 Ops console ┘        │           ├─► Redis (rate limits, cache)
                      │           └─► Inngest (durable workflows: timers, retries)
                      │
                      ▼  adapters (one module per provider, mockable in dev/tests)
   Claude API · Voyage embeddings · Instagram API · Razorpay / RazorpayX
   KYC (Cashfree Secure ID) · e-sign (Leegality) · WhatsApp (Gupshup/Meta)
   MSG91 SMS · SES email · Shopify · scraping fallback (Firecrawl)
```
Every external service sits behind an **adapter** with a mock version. That means the full product can run and be tested before every contract and API key is in place, and a provider can be swapped without touching business logic.

---

## 2. APIs and services

### 2.1 AI

| Need | API | How we use it |
|---|---|---|
| Understand product/brand from URL or images | **Claude API** (`claude-opus-5`, structured JSON output; reads images too) | Extract product name, category, features, benefits, claims, target audience; map to our niche taxonomy; flag restricted categories and risky claims ("cures", "clinically proven") |
| Scripts, hooks, shot lists, captions, hashtags | **Claude API** | Generates the creator brief for each creator, in English, Hindi or Hinglish, matched to their style |
| Content compliance check before posting | **Claude API** (vision on video frames + caption text) | Checks disclosure present, no claims beyond the confirmed brief, product/logo visible, brand-safety |
| Match explanations and dashboard insights | **Claude API** | "Why this creator", "why this post did well", "Explain this" assistant |
| Comment sentiment and top questions | **Claude API** (Message Batches API: 50% cheaper, runs in the background) | Daily batch over new comments |
| Content similarity for matching | **Voyage AI embeddings** (text + multimodal), stored in pgvector | Embed creator captions/transcripts/thumbnails and product briefs; similarity feeds the match score. Anthropic recommends Voyage for embeddings since Claude doesn't provide them |
| Speech-to-text of creator Reels | **Sarvam AI** (strong on Indian languages and Hinglish) or self-hosted Whisper | Transcripts improve niche detection and similarity |
| Content provenance | **C2PA** open-source SDK | Adds "AI-assisted" credentials to files where AI generated visuals |
| Phase 2: AI video/avatars (Mode C) | Evaluate **HeyGen**, **Google Veo**, **Runway**; **ElevenLabs** for Hindi/English voice | Only for brand-owned AI UGC; never a real creator's likeness without per-asset approval |

Model choice: the plan uses `claude-opus-5` everywhere for best quality. High-volume, simple jobs like comment tagging could move to a cheaper model (`claude-haiku-4-5`) later if costs matter. That's your call once we see real volumes.

### 2.2 Social (Instagram / Meta)

| Need | API | Notes |
|---|---|---|
| Creator login and account connect | **Instagram API with Instagram Login** (scopes: `instagram_business_basic`, `instagram_business_content_publish`, `instagram_business_manage_insights`, `instagram_business_manage_comments`) | Creator/Business accounts only; we guide creators to switch (free, 1 minute) |
| Profile, media, audience demographics | Instagram Graph API: user, media and insights endpoints | Refresh daily; long-lived tokens (~60 days) auto-refreshed |
| Publishing Reels/posts/stories | Content Publishing API (create container → publish) | Daily per-account publishing cap; video must be at a public URL (S3 signed URL) |
| Post verification and metrics | Media + insights endpoints; **webhooks** for comments/mentions | Daily checks during 7-day window, then weekly |
| Paid-ads usage (whitelisting) | **Meta Marketing API**: partnership ads using the creator's post | Creator grants partner access in the Instagram app; we track it and remind them |
| Requirements | **Meta Business Verification + App Review** | Weeks of lead time: the #1 launch blocker, so start in week 1 |

**Optional, and very useful for cold start:** a creator-data provider such as **Modash**, **HypeAuditor** or **Phyllo** for fake-follower/authenticity scores and audience estimates. We can then score creators before they even connect and avoid building fraud detection from scratch in the MVP.

### 2.3 Money (India)

| Need | API | Notes |
|---|---|---|
| Brand payments (UPI, cards, netbanking) | **Razorpay Payment Gateway** (alt: Cashfree PG) | Orders API + webhooks (signature verified); GST invoice generated by us |
| Creator payouts | **RazorpayX Payouts** (alt: Cashfree Payouts) | Bank/UPI transfer after verification; UTR shown to creator |
| Bank account verification | RazorpayX Fund Account Validation (penny drop) or Cashfree | Confirms name matches before first payout |
| Accounting, invoices, TDS | **Zoho Books API** (or Tally export) + CA-run TDS filing | E-invoicing via a GSP (e.g. ClearTax) once turnover crosses the threshold |

### 2.4 Identity, contracts, communication

| Need | API | Notes |
|---|---|---|
| KYC: PAN, GSTIN, Aadhaar via DigiLocker, bank | **Cashfree Secure ID** (alt: Signzy, IDfy) | Same vendor as payouts keeps it simple |
| E-signing contracts | **Leegality** or **Digio** (OTP e-sign, Aadhaar eSign for bigger deals) | Signed PDF + audit trail stored in S3 |
| WhatsApp notifications and one-tap approvals | **WhatsApp Business Platform** via a BSP (**Gupshup**, Interakt or AiSensy) | Pre-approved message templates; buttons for accept/approve |
| SMS OTP | **MSG91** | DLT registration is mandatory in India (lead time) |
| Email | **AWS SES** (or Resend) | Transactional emails, weekly reports |

### 2.5 Brand integrations and utilities

| Need | API | Notes |
|---|---|---|
| Product page reading | Own fetcher (schema.org / OpenGraph / Shopify JSON) + **Playwright**; fallback **Firecrawl** | With protection against internal-network (SSRF) requests |
| Sales attribution | **Shopify Admin API** + order webhooks (discount codes per creator); WooCommerce REST | Per-creator revenue and ROAS on the dashboard |
| Link tracking | Own short-link service with UTM tags | Click counts per creator |
| Royalty-free music for API-posted Reels | A licensed library (e.g. Epidemic Sound / Artlist); check commercial API licence | Instagram's music library isn't available for API posts |

---

## 3. Task list (MVP)

Sized for the MVP described in PRODUCT_PLAN §14 (about 12 weeks of build). Each epic ends with working, tested software. The order matters: later epics depend on earlier ones.

### Epic 0: Foundations (week 1)
- [ ] Repo structure, TypeScript, lint, formatting, GitHub Actions CI
- [ ] Postgres + Prisma schema v1, migrations, seed data
- [ ] Auth: email + phone OTP, roles (brand / creator / ops), sessions
- [ ] Design system (Tailwind + shadcn), layouts for the three apps
- [ ] Adapter pattern + mocks for every external service
- [ ] Audit/event log (every state change recorded); feature flags; error monitoring

### Epic 1: Niche taxonomy and onboarding (weeks 2-3)
- [ ] Niche taxonomy: 15+ categories with sub-niches (beauty, skincare, fashion, fitness, food, travel, tech, gaming, parenting, finance, education, lifestyle, home decor, health/wellness, pets, automotive, comedy/entertainment, sports, regional/language)
- [ ] Creator onboarding: Instagram connect, stats and audience sync, AI-suggested niches from recent posts, rate card, red-line categories, AI preferences, KYC (PAN, bank), agreement e-sign
- [ ] Brand onboarding: domain verification, GSTIN/PAN KYC, brand profile, restricted-category check, agreement e-sign
- [ ] Ops review queue for creators and brands

### Epic 2: Creator data pipeline (weeks 3-4)
- [ ] Daily sync of media, insights and audience
- [ ] Reel transcription, embeddings (Voyage → pgvector)
- [ ] Authenticity score (own rules and/or Modash/HypeAuditor), brand-safety scan of recent posts
- [ ] Token refresh and "reconnect Instagram" flow

### Epic 3: Campaign creation and product understanding (week 4)
- [ ] Campaign form: objective, budget, deliverables, audience, timeline, must-say/must-not-say, usage rights (incl. paid ads)
- [ ] Product URL fetcher (structured data first, SSRF-safe) + image upload
- [ ] Claude brief extraction, niche mapping, claims and restricted-category flags
- [ ] Brief review and confirm screen (versioned)

### Epic 4: Matching engine (weeks 5-6)
- [ ] Hard filters (niche, geo, gender/age fit, budget, content mode, red lines, competitor conflicts, capacity, authenticity, account health)
- [ ] Weighted scoring (audience fit, content similarity, performance, reliability, price efficiency, saturation)
- [ ] Budget optimiser (best set of creators within budget; tier mix)
- [ ] Explanations ("why this creator"), backups per slot, "not enough creators" state
- [ ] Tests with synthetic creators; tuning dashboard for ops

### Epic 5: Pricing, contracts and consent (week 6)
- [ ] Margin engine: brand price = creator fee ÷ (1 − margin), global and per-campaign setting; rounding rules
- [ ] Strictly separated brand and creator data views, enforced at the database/API level, with tests proving neither side can see the other's number
- [ ] Contract templates (brand order, creator campaign agreement incl. paid-ads usage rights, minimum live period, non-circumvention)
- [ ] E-sign integration; consent ledger (every consent with document hash, time, IP)

### Epic 6: Offers and workflow engine (weeks 7-8)
- [ ] Campaign state machine (PRODUCT_PLAN §6) on Inngest
- [ ] Offers with 48h expiry → automatic backup offers
- [ ] Deadlines, reminders, replacement and refund rules
- [ ] Notifications: in-app, email, WhatsApp templates, SMS

### Epic 7: Payments and payouts (week 8)
- [ ] Checkout (Razorpay), webhooks, GST invoices
- [ ] Internal ledger (held → released → paid), refunds
- [ ] Payouts (RazorpayX) with TDS deduction, bank verification, UTR tracking
- [ ] Earnings statements and TDS certificates for creators

### Epic 8: Content production and approvals (weeks 9-10)
- [ ] AI creator brief (script, hooks, shot list, caption) per creator
- [ ] Upload drafts (large video upload direct to S3), FFmpeg processing to Instagram specs
- [ ] Automated checks (disclosure, claims vs brief, logo/product presence, brand safety)
- [ ] Brand review with inline feedback (2 revision rounds, 72h auto-approve), creator final approval (asset hash recorded)

### Epic 9: Publishing and verification (week 10)
- [ ] Scheduled publishing via Instagram API; self-post fallback with link verification
- [ ] Partnership-ads access tracking and reminders
- [ ] 7-day daily verification (exists, public, disclosure intact), then weekly until minimum live period; hold/clawback flows
- [ ] Metrics sync for dashboards

### Epic 10: Dashboards and reports (weeks 11-12)
- [ ] Brand: home, campaign detail, content library with usage-rights expiry, billing, PDF report
- [ ] Creator: home, offers, workspace, earnings, consent centre
- [ ] Ops: funnel, stuck queue, disputes, payouts, integration health

### Epic 11: Hardening and launch (week 12)
- [ ] Security review (auth, file uploads, SSRF, rate limits, PII encryption for PAN/bank)
- [ ] End-to-end tests of the full campaign lifecycle
- [ ] Load test on matching and dashboards; backups and restore drill
- [ ] Legal pages (terms, privacy notice per DPDP, creator and brand agreements) in the app

### Non-engineering tasks with long lead times (you; start in week 1)
| Task | Why it matters | Typical lead time |
|---|---|---|
| Register company (Pvt Ltd), current bank accounts (operations + creator payables), GST registration | Needed for Razorpay, Meta verification and invoices | 2-4 weeks |
| **Meta Business Verification + App Review** for Instagram permissions | Without it we can't publish or read insights for real creators | 2-6 weeks, sometimes several rounds |
| Razorpay + RazorpayX activation (business KYC) | Collect and pay money | 1-2 weeks |
| WhatsApp Business account via a BSP + template approvals | Main channel for creators | 1-2 weeks |
| DLT registration for SMS (MSG91) | Legal requirement for SMS OTP in India | 1-2 weeks |
| KYC and e-sign vendor contracts (Cashfree Secure ID, Leegality/Digio) | Onboarding and contracts | 1-2 weeks |
| Lawyer: creator agreement, brand agreement, usage-rights/paid-ads clause, privacy notice, terms | Consent and contracts must hold up | 2-4 weeks |
| Chartered accountant: GST on principal model, TDS section, invoice formats | Avoid tax mistakes | 1-2 weeks |
| Creator seeding: recruit 200-500 nano/micro creators across niches before brand launch | A marketplace with no supply can't match | Ongoing from week 1 |
| Anthropic API key, Voyage API key, AWS account | AI features and hosting | Same day |

---

## 4. What I need from you to start building

Nothing, to begin. I'll build with **mock adapters**, so the whole flow (onboarding → matching → contracts → payment → approval → publish → verification → payout → dashboards) works end to end on demo data. Each real service gets switched on as its account is ready:

1. **Now (optional):** Anthropic API key (real AI brief extraction and scripts instead of simple rules).
2. **When available:** Meta app credentials, Razorpay/RazorpayX test keys, WhatsApp BSP credentials, KYC and e-sign sandbox keys, AWS account.

Secrets are never committed to the repo; they go into environment variables.
