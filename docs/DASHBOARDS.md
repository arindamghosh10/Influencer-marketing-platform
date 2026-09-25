# Dashboards and Analytics Spec

> Companion to [PRODUCT_PLAN.md](PRODUCT_PLAN.md). This spec defines what brands, creators and the ops team see, where the numbers come from, and how the product explains them so nobody has to guess what a number means or what happens next.

---

## 1. Design principles

1. **Every number is explained.** Each metric has an ⓘ tooltip showing its definition, formula, data source and last-updated time (see the glossary in §6).
2. **Status comes with a next step.** Every state shows *what is happening*, *who we're waiting on*, *by when*, and *what happens if nothing happens*. Example: "Waiting for Priya to approve the final video. Due in 18h. If not approved, we'll offer this slot to your backup creator."
3. **Money is always traceable.** Every rupee can be followed from the brand's payment → escrow → creator payout, with a status and date at each step.
4. **Plain-language AI insights on top, raw data underneath.** Example: "This Reel's watch-through rate is 2× your campaign average. The hook in the first 2 seconds is the likely reason." A "See data" link sits under each insight.
5. **Benchmarks, not just totals.** Compare each result to the campaign average, the niche benchmark, and the platform's prediction at booking time.
6. **Privacy by role.** Each side sees only what it is entitled to (see §5).
7. **Mobile-first for creators, desktop-first for brands.**
8. **Exportable.** CSV and PDF on every table and report. Brands can also get a scheduled weekly email report.

---

## 2. Brand dashboard

### 2.1 Home (overview)
| Widget | Content |
|---|---|
| **Action required** (top, sticky) | Items waiting on the brand, each with a due time and a one-click action: confirm brief, pick creators, pay, review content, respond to a dispute |
| **KPI tiles** (date range selector) | Total spend · Posts live · Total reach · Total views · Engagements · Avg engagement rate · CPM · CPE · Link clicks · Conversions / revenue (if tracking is connected) |
| **Campaign list** | Each campaign with a stage progress bar (Brief → Matching → Offers → Content → Review → Live → Verified → Closed), health indicator (on track / at risk / blocked), spend vs budget |
| **AI insights feed** | 3 to 5 plain-language insights (e.g. "Micro creators delivered 38% cheaper CPM than mid-tier in your last 3 campaigns") |
| **Upcoming** | Scheduled posts calendar for the next 14 days |

### 2.2 Campaign detail
**a) Summary header**: objective, budget, spend so far, timeline, confirmed product brief (view version), content mode, disclosure/compliance status.

**b) Timeline and activity log**: every event with a timestamp: brief confirmed, offers sent, creator accepted, payment captured, draft uploaded, revision requested, approved, published, verification day 1…7, payout released. The same log is used for disputes, so what the brand sees is exactly what ops sees.

**c) Creator slots table**
| Column | Example |
|---|---|
| Creator (handle, tier, niche) | @priya.skin · Micro · Skincare |
| Why matched | "82% audience women 18-34 · 71% in your target cities · high skincare content overlap" |
| Status plus next step | "Draft due in 2 days" |
| Fee | ₹12,000 |
| Predicted vs actual | Reach 40k predicted → 52k actual ▲30% |
| Post link and date | |
| Verification | Day 4 of 7 ✔ live, disclosure present |

**d) Performance** (per campaign and per post)
- Reach, impressions/views, likes, comments, shares, saves, profile visits, follows (if available), watch time / avg watch %, 3-second hold rate (Reels).
- Charts: cumulative views over time per post, engagement rate by creator, CPM/CPE by creator tier.
- **Predicted vs actual** for every post, so brands learn how well matching works and trust it more over time.
- **Comment sentiment and themes** (AI): positive/neutral/negative split, top questions ("price?", "works on oily skin?"), purchase-intent comments. Brand-safety alerts on harmful comment spikes.

**e) Conversions** (optional integrations)
- Unique UTM link and **unique discount code per creator**, which gives per-creator attribution.
- Shopify / WooCommerce integration: orders, revenue, **ROAS** per creator and per campaign.
- A pixel/Conversions API for non-Shopify sites comes later.
- Clear note: "Attribution covers only tracked clicks and codes. Real impact is usually higher (people search the brand directly)."

**f) Audience delivered**: the aggregated audience of the posts that ran (age, gender, top cities), compared with the brand's target. Answers "did we reach the right people?"

### 2.3 Content library
- All approved assets (final files, captions, versions, approval history).
- **Usage rights for every asset**: allowed channels, expiry date, paid-ads permission, with a countdown and an "extend rights" button (which generates the mini-agreement and payment).
- Download originals. C2PA/AI label shown where applicable.

### 2.4 Billing and payments
- Invoices (GST-compliant) and receipts.
- **Money flow per campaign**: Paid → in escrow → released to creator X on date → refunded (reason).
- Refunds and credits, with the rule that applied (e.g. "Creator missed deadline, slot refunded 100%").
- Payment methods, spend limits, downloadable ledger.

### 2.5 Creator discovery and relationships
- Browse and search creators (only public/profile-level stats and aggregated audience data are visible before booking).
- Shortlists, favourites, "work again" list, past collaborations with results.
- Ratings given and received.

### 2.6 Reports
- Auto-generated **campaign report** at close (PDF plus shareable link): summary, what worked, best-performing creator and content, learnings, and recommendations for the next campaign with a suggested budget split.
- Scheduled weekly/monthly email digests.

### 2.7 Compliance and documents
- Signed agreements, consent records per asset, disclosure checks passed, brief versions. The same evidence pack is used in disputes.

---

## 3. Creator dashboard (mobile-first)

### 3.1 Home
| Widget | Content |
|---|---|
| **Action required** | Accept/decline offers (with deadline), upload draft, approve final asset, reconnect Instagram, complete KYC |
| **Earnings tiles** | Available / Pending (in verification, with a countdown "₹12,000 releases in 3 days") / Paid this month / Lifetime |
| **Active campaigns** | Stage, next step, due date |
| **Profile health** | Instagram connection status, KYC status, authenticity score, reliability score, with tips to improve each |

### 3.2 Offers
- Full brief before accepting: brand, product, deliverables, fee (net after TDS shown clearly), timeline, usage rights, exclusivity, content mode (and whether AI likeness is involved), minimum live period.
- A **"Why you were matched"** explanation, and brand ratings from other creators.
- Accept, decline (with a reason, which improves future matching), or counter-offer (Phase 2).

### 3.3 Campaign workspace
- Brief, AI-generated script/hooks/shot list, brand do's and don'ts.
- Upload drafts, see feedback inline, revision count ("1 of 2 revisions used").
- Final approval screen: exact video, caption and scheduled time, with an "Approve and schedule" button. The consent record is created here.
- After posting: **verification tracker** (Day 1 ✔ … Day 7), with a warning if the post is missing or the disclosure was removed.

### 3.4 Earnings and payouts
- Every payment with gross fee, TDS deducted, GST (if applicable), net amount, status, and UTR/bank reference.
- Downloadable TDS certificates, a yearly earnings statement, and invoices (auto-generated for GST-registered creators).
- Clear timeline explaining *why* money is pending and *when* it releases.

### 3.5 Performance and growth insights
- Per sponsored post: reach, views, engagement, saves, shares, compared with the creator's own organic average.
- **Rate insights**: "Creators with your audience size and engagement in Skincare earn ₹8k to ₹14k per Reel. You're at ₹10k."
- **Match insights**: why offers were declined or missed (e.g. "Your audience is 60% outside the brand's target cities"), with tips.
- Reliability score breakdown (on-time %, response time, revision rounds).

### 3.6 Profile and settings
- Niches, rate card, red-line categories, availability / "on break" toggle, max concurrent campaigns.
- **Consent centre**: every consent given, with date and scope; AI/likeness permissions toggles; revoke button; download all my data (DPDP).

---

## 4. Ops / admin console (internal)

- **Funnel**: campaigns by state, conversion between states, median time in each state.
- **Stuck queue**: workflows past their SLA (e.g. offer pending over 48h, verification failed).
- **Disputes**: evidence pack, timeline, resolution actions (refund / release / partial).
- **Trust and safety**: fraud flags, fake-follower alerts, brand-safety content flags, KYC review queue.
- **Payments**: escrow balance, payouts due today, failed payouts, chargebacks.
- **Integrations health**: Meta API errors and rate limits, expiring tokens, WhatsApp delivery rate.
- **Matching quality**: predicted vs actual error, offer acceptance rate by rank, coverage per niche (where supply is short).
- **Business KPIs**: GMV, take rate, revenue, repeat brand rate, creator NPS.

---

## 5. Data visibility rules (who sees what)

| Data | Brand (before booking) | Brand (booked creator) | Creator | Ops |
|---|---|---|---|---|
| Creator public stats (followers, avg engagement) | ✔ | ✔ | ✔ | ✔ |
| Creator audience demographics | Aggregated only | ✔ Aggregated | ✔ | ✔ |
| Creator per-post insights for campaign posts | ✗ | ✔ | ✔ | ✔ |
| Creator organic post insights | ✗ | ✗ | ✔ | ✔ (support only) |
| Creator KYC / bank / PAN | ✗ | ✗ | ✔ | ✔ (restricted role) |
| Creator fee (what the creator receives) | ✗ | ✗ | ✔ | ✔ |
| Brand price (what the brand pays) | ✔ | ✔ | ✗ | ✔ |
| Brand sales / revenue data | n/a | Brand only | ✗ (optional: see "your code drove 42 orders") | Aggregated |
| Other brands' campaigns | ✗ | ✗ | ✗ | ✔ |

- Sharing insights and audience data with brands is part of the creator's consent at onboarding and campaign acceptance (see PRODUCT_PLAN §8).
- Contact details (phone/email) stay masked; communication goes through in-app chat.

---

## 6. Metric glossary (source of truth for tooltips)

| Metric | Definition / formula | Source | Refresh |
|---|---|---|---|
| Reach | Unique accounts that saw the post | Instagram insights | Every 6h for 7 days, then daily for 30 days, then weekly |
| Views / Impressions | Total times shown/played | Instagram insights | Same |
| Engagements | Likes + comments + shares + saves | Instagram insights | Same |
| Engagement rate (ER) | Engagements ÷ Reach × 100 (by reach, not followers, and labelled as such) | Derived | Same |
| CPM | Spend ÷ Views × 1000 | Derived | Same |
| CPE | Spend ÷ Engagements | Derived | Same |
| CPC | Spend ÷ Link clicks | Platform short-link / UTM | Real time |
| Conversions | Orders using creator code or UTM | Shopify/Woo integration | Hourly |
| ROAS | Attributed revenue ÷ Spend | Derived | Hourly |
| Avg watch % | Avg watch time ÷ video length | Instagram insights (Reels) | Every 6h |
| Predicted reach | Model estimate at booking time | Matching model | Fixed at booking |
| Authenticity score | 0-100; share of real, active followers and organic engagement | Platform model | Monthly |
| Reliability score | On-time delivery, response time, revisions, disputes | Platform | After each campaign |
| Verification status | Post exists, public, not edited to remove disclosure | Daily API check | Daily for 7 days, weekly until min live period |

Every widget shows a **"last updated"** time. If data is stale (e.g. the Instagram token expired), a banner explains why and who needs to act.

---

## 7. Help and education inside the dashboards

- **Onboarding tours** for first-time users (3-5 steps per dashboard).
- **"What happens next" panel** on every campaign and offer, generated from the workflow state.
- **Explain-this button (AI assistant)**: ask "Why did this post underperform?" or "Why is my payout pending?" It answers from the user's own data and the rules above, and links to the source.
- **Help centre articles** linked contextually: how matching works, escrow and payouts, TDS/GST, usage rights, disclosure rules, AI content policy.
- **Benchmarks page**: average ER, CPM and rates by niche and tier, refreshed monthly from platform data (anonymised).

---

## 8. Notifications tied to dashboards

| Event | Brand | Creator |
|---|---|---|
| Offer sent / expiring | – | WhatsApp + push + email |
| Creator accepted / declined / replaced | In-app + email | – |
| Draft ready for review / revision requested | In-app + email | WhatsApp + push |
| Final approval needed | – | WhatsApp + push (one tap) |
| Post live | In-app + email (with link) | Push |
| Verification issue (post missing / disclosure removed) | In-app | WhatsApp + push (urgent) |
| Payout released | – | WhatsApp + SMS with amount and UTR |
| Weekly performance digest | Email | Email |
| Usage rights expiring (14 days) | Email | – |

Users control non-critical notifications. Critical ones (money, deadlines, compliance) are always on.

---

## 9. Technical notes

- **Metrics pipeline**: a scheduled job pulls Instagram insights per post on a decaying schedule (§6) and stores them as `MetricSnapshot` rows (time series). Dashboards read from pre-aggregated tables/materialised views, never from Meta live.
- **Analytics store**: Postgres is fine for MVP. Move heavy aggregates to ClickHouse/BigQuery when the snapshot count grows.
- **Charts**: one charting library across all dashboards (e.g. Recharts / ECharts) with a shared theme and accessible colours.
- **Access control**: all dashboard queries go through a role-and-ownership filter (row-level security in Postgres) so the rules in §5 are enforced in the database, not just in the UI.
- **Report generation**: HTML templates rendered to PDF; shareable read-only links with expiry.

---

## 10. Phasing

| Phase | Brand | Creator | Ops |
|---|---|---|---|
| MVP | Home, campaign detail (status, timeline, slots, core metrics), content library, billing, PDF report | Home, offers, workspace, earnings with TDS, basic post stats | Funnel, stuck queue, disputes, payouts |
| Phase 2 | Conversions (Shopify, codes, UTM), comment sentiment, AI insights, benchmarks, usage-rights extension | Rate and match insights, reliability breakdown, AI explain-this | Matching quality, T&S console |
| Phase 3 | Multi-brand agency view, API/exports to BI tools, scheduled reports | Growth coaching, multi-platform stats | Advanced forecasting |
