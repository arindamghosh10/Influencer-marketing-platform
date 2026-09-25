# Influencer Marketing Platform: Product Plan (v1)

> Working name: **"the Platform"**. A two-sided marketplace where brands describe a product, get matched with the right creators, pay once into escrow, and receive AI-assisted UGC ads that are published on the creators' Instagram accounts. Creators are paid automatically once the post is verified.

---

## 0. TL;DR: what changed from the original idea

| Original idea | Problem | Improved plan |
|---|---|---|
| AI creates the UGC ad and we post it on the influencer's Instagram | Posting AI content that shows a real person's face or voice without their clear, per-post approval is a deepfake and likeness-rights problem. It breaks trust, Meta's policies and disclosure law (ASCI/FTC, EU AI Act Art. 50, India's IT Rules on synthetic content). | **Three content modes** (§4). **Nothing is ever posted without the creator approving that exact asset and caption.** Consent is recorded per campaign, not once at signup. |
| Match on "niche" | One niche label is too coarse. A "fitness" creator with a 70% male audience in Delhi is wrong for a women's skincare brand in Bangalore. | Multi-signal matching (§5): hard filters, then a score (audience fit, content similarity, performance, authenticity, price, brand safety), then a check that the shortlist is varied, then an explanation of every pick. |
| Pay influencer after 7 days | What if they delete the post on day 8? What if the brand's card is charged back? What about tax? | Escrow at checkout. A **7-day verification window** during which the post is checked automatically every day. A **minimum live period** (e.g. 30/90 days) in the contract, with clawback. Automatic TDS/GST handling (§7). |
| Brand gives URL, app understands it | Scraping fails on many sites, and the LLM can hallucinate product claims. | Structured extraction first, LLM second. The **brand confirms the generated brief** before anything else happens. Claims and restricted categories are checked automatically (§3). |
| Client pays, then we generate and post | Creators may not respond, may reject, or may be unavailable. | Offers go out first. **Payment is captured only for creators who accepted.** Timeouts automatically bring in backup creators (§6). |

---

## 1. Personas and goals

| Persona | Wants | Fears |
|---|---|---|
| **Brand (D2C founder / marketing manager)** | Fast, cheap, authentic-looking UGC; predictable results; no negotiation back-and-forth | Paying for fake followers, off-brand content, creators going silent, compliance trouble |
| **Agency** (later) | Manage many brands; white-label reports | Margin squeeze; losing client ownership |
| **Creator / Influencer** | Steady, fair-paying deals that fit their audience; on-time pay; no extra work | Their face used in something they didn't approve; late or no payment; brands that damage their reputation |
| **Platform Ops / Trust & Safety** | Low dispute rate, low fraud, scale without adding headcount | Legal exposure, chargebacks, Meta API bans |

**North-star metric:** *Verified live posts per week* (a campaign that reached a paid, verified post). Everything in the funnel serves this number.

---

## 2. Onboarding

### 2.1 Creator onboarding
1. **Sign up** with phone and email OTP.
2. **Connect Instagram** via Meta's official login (Instagram API with Instagram Login, or Facebook Login for Business). The account must be a Business or Creator account; show a one-tap guide for switching.
   - Pulls: follower count, media, reach, engagement and **audience demographics** (age, gender, city, country, which Meta provides for accounts above a follower threshold).
   - We never ask for the Instagram password.
3. **Identity and payout KYC**: legal name, PAN (India) / tax ID, bank account verified with a penny-drop test, and age 18+ (block minors entirely in v1). Aadhaar/DigiLocker-based verification is optional.
4. **Niche and profile**: pick 1 primary and up to 3 secondary niches from a **hierarchical taxonomy** (e.g. `Beauty > Skincare > Acne-care`). The AI **proposes** niches from their last 50 posts and the creator confirms. This stops people claiming niches that don't match what they post.
5. **Rate card**: price per Reel, Story or Post, and whether they allow usage rights for ads (whitelisting / paid boosting) at an extra cost. The platform suggests a price band from their stats.
6. **Content preferences and red lines**: categories they will never promote (alcohol, gambling, crypto, fast fashion, etc.), competitor exclusivity, languages, whether they film content themselves.
7. **AI and likeness preferences** (the key consent screen, §8):
   - `Mode A only`: I make my own content; AI can help with scripts only.
   - `Mode B allowed`: AI may generate content featuring my likeness **for review**, per campaign.
   - Optional: record a **voice/face sample** for a digital twin (Phase 3 only, separately consented, revocable).
8. **Creator agreement**: clickwrap plus e-sign, versioned (see §8).
9. **Automated checks** before going live: fake-follower and authenticity score, brand-safety scan of recent posts (hate, adult, violence, misinformation), duplicate-account detection. Creators are Approved, sent to Manual review, or Rejected.

### 2.2 Brand onboarding
1. Sign up with a work email and **verify domain ownership** (DNS TXT record or a link sent to an email on that domain). This stops people impersonating brands.
2. Business KYC: company name, GSTIN / VAT, PAN, billing address, authorised signatory.
3. Brand profile: niches (same taxonomy), target audience, tone of voice, logo, brand guidelines PDF, do/don't words, competitors.
4. **Category check**: restricted categories (alcohol, gambling, pharma/Rx, supplements with health claims, financial products, crypto, weapons, adult, political) are either blocked or routed to manual review with extra documentation (licences, claim substantiation).
5. Brand agreement: clickwrap plus e-sign.

---

## 3. Campaign creation: understanding the brand and product

### 3.1 Inputs
- Product URL **or** images plus text, or both.
- Objective: awareness / engagement / traffic / sales / content-only (brand just wants the assets).
- Budget (total), timeline, target geography, audience, number of creators (or "let the platform decide").
- Deliverables: Reel, Story, carousel; count; duration; whether paid usage rights are needed.
- Must-say points, must-not-say points, discount code or UTM link.

### 3.2 Product understanding pipeline
```
URL ──► fetch (headless browser, respects robots) ──► structured data first:
         • schema.org Product JSON-LD, OpenGraph tags
         • Shopify /products/<handle>.json, WooCommerce REST if available
       ──► LLM extraction (name, category, price, features, benefits, claims, target user)
       ──► image understanding (packaging, colours, usage context)
       ──► category classifier ─► restricted? ─► block / manual review
       ──► claims checker ─► flags "cures", "100% guaranteed", "clinically proven" (needs proof)
       ──► PRODUCT BRIEF (editable)  ──► brand must confirm ✔
```
- **The brand must confirm the brief** before matching. This is the single most important guard against AI hallucinations ending up in an ad.
- If scraping fails (bot protection, login wall), fall back to asking for images plus a 3-question form.
- Store every brief version. The confirmed version is what content is checked against later.

---

## 4. Content modes (the biggest product decision)

| Mode | Who creates | AI role | Posting | Launch phase |
|---|---|---|---|---|
| **A: Creator-made (default)** | Creator films | AI writes the brief, hooks, script and shot list, and suggests captions and hashtags; AI does edit polish and subtitles | Auto-publish via API **after creator and brand approve**, or the creator posts and we verify | MVP |
| **B: AI-assisted with creator's likeness** | AI generates from the creator's approved assets (their photos/b-roll plus product shots) or a licensed digital twin | Full generation | Only after the creator approves the exact final asset | Phase 2 to 3 |
| **C: Brand-owned AI UGC** | AI avatars / virtual creators (no real person's likeness) | Full generation | Posted on brand's account, or distributed by creators as clearly labelled brand content | Phase 2 |

Why Mode A is the default:
- Authentic UGC performs better, and audiences and Meta increasingly detect and label AI content.
- It avoids most likeness and deepfake legal risk while you are small.
- AI still removes 80% of creator effort (script, hooks, editing), which is the real value to creators.

Rules that apply to every mode:
- **Mandatory disclosure**: `#ad` / `Paid partnership` label, plus an **AI-generated label** whenever synthetic media is used (Meta's "AI info" label, C2PA content credentials embedded in the file).
- Automated pre-publish checks: brand-safety, claims check against the confirmed brief, logo/product presence (vision model), music copyright (use only licensed or royalty-free audio in API posts), caption length and hashtags.
- **Revision rounds**: 2 included; more cost extra.

---

## 5. Matching algorithm

### 5.1 Pipeline
```
All approved creators
  │
  ├─ 1. HARD FILTERS (must pass all)
  │     • niche compatibility (taxonomy distance ≤ threshold)
  │     • geography: ≥ X% audience in target country/cities
  │     • rate ≤ per-creator budget ceiling
  │     • content mode compatibility (brand wants B, creator allows only A → out)
  │     • creator red lines (category blocklist) and brand blocklist
  │     • competitor exclusivity conflicts (creator promoted a competitor in last N days)
  │     • availability / capacity (max active campaigns; not on break)
  │     • authenticity score ≥ threshold; brand-safety pass; account health (token valid)
  │     • language
  │
  ├─ 2. SCORING (weighted, learned over time)
  │     S = w1·AudienceFit + w2·ContentSimilarity + w3·PredictedPerformance
  │       + w4·Reliability + w5·PriceEfficiency + w6·BrandSafety − w7·Saturation
  │
  ├─ 3. BUDGET OPTIMISATION: choose the set of creators (knapsack) that maximises
  │     predicted objective (reach / engagement / conversions) within the budget
  │
  ├─ 4. DIVERSITY and FAIRNESS: mix of tiers (nano/micro/mid), don't always
  │     surface the same top creators; reserve slots for promising new creators
  │
  └─ 5. EXPLANATION: "Why this creator": 3 bullet reasons plus a risk note
```

### 5.2 Signals
| Signal | Source | Notes |
|---|---|---|
| AudienceFit | Instagram audience demographics vs brand target | Cosine similarity over age × gender × geo distribution |
| ContentSimilarity | Embeddings of creator's captions, transcripts and thumbnails vs product brief embedding | pgvector; catches "fitness creator who talks a lot about skincare" |
| PredictedPerformance | Historic engagement rate, reach per follower, past campaign results on the platform | Normalise by follower tier; engagement rate differs heavily by size |
| Reliability | On-time delivery %, response time, revision count, disputes | Cold start: neutral prior, small boost for verified new creators |
| PriceEfficiency | Predicted reach ÷ price (CPM-equivalent) | |
| BrandSafety | Scan of last 90 days of content and comments | |
| Saturation | Number of sponsored posts in last 30 days | Heavy ad load hurts results and credibility |
| Authenticity | Follower growth anomalies, follower/engagement ratio, comment quality (bot comments) | Fake-follower detection is essential |

### 5.3 How we avoid "problems in future"
- **Two-sided acceptance**: a match is only a proposal. The creator sees the full brief and accepts or declines. Nobody is forced into a campaign.
- **Pre-flight conflict check** repeated at acceptance time and again just before posting (the creator could have signed a competitor deal in between).
- **Feedback loop**: after every campaign, both sides rate each other and actual metrics are compared with the prediction. Weights are retrained monthly. Start with hand-tuned weights and switch to a learning-to-rank model once you have ~500 completed campaigns.
- **Backups**: the matcher always returns ranked **backups** for each slot.

---

## 6. Campaign lifecycle (state machine)

Build this as a **durable workflow** (e.g. Temporal, or a DB-backed state machine with a job queue). There are long waits (48h responses, 7-day verification, 30-day live checks) that must survive restarts.

```
DRAFT
  └─► BRIEF_CONFIRMED            (brand confirmed AI brief)
        └─► SHORTLISTED          (matcher produced picks + backups; brand selects)
              └─► OFFERS_SENT    (creators notified: WhatsApp/email/push/in-app)
                    │  timeout 48h / decline ──► auto-offer next backup
                    └─► ACCEPTED (creator e-signs campaign agreement)
                          └─► PAYMENT_CAPTURED (escrow; only for accepted creators)
                                └─► CONTENT_IN_PROGRESS  (mode A: creator uploads; B/C: AI generates)
                                      └─► AUTO_CHECKS   (safety, claims, disclosure, logo, audio)
                                            └─► BRAND_REVIEW  (72h; silence = auto-approve, told upfront)
                                                  │  revision (≤2) ──► back to CONTENT_IN_PROGRESS
                                                  └─► CREATOR_FINAL_APPROVAL  (mandatory, explicit)
                                                        └─► SCHEDULED
                                                              └─► PUBLISHED  (API or creator self-post + link)
                                                                    └─► VERIFYING (7 days, daily checks)
                                                                          ├─ post removed/edited ─► DISPUTE / HOLD
                                                                          └─► PAYOUT_RELEASED
                                                                                └─► LIVE_MONITORING (until min live period)
                                                                                      └─► CLOSED (report sent)
Side branches from any state: CANCELLED (rule-based refunds) · DISPUTE (ops) · EXPIRED
```

### 6.1 Timeouts and fallbacks (so nothing gets stuck)
| Situation | Automatic action |
|---|---|
| Creator doesn't respond to offer in 48h | Offer expires; next backup is offered; brand is notified |
| Creator accepts but misses content deadline | Reminder at T-48h and T-24h; at deadline plus 24h: replace creator, refund or reallocate that slot, reliability score reduced |
| Brand doesn't review in 72h | Auto-approve (stated in the brand agreement) |
| Creator rejects final AI asset twice | Switch to Mode A for that creator or replace; brand not charged extra |
| Instagram token expired / permission revoked | Ask the creator to reconnect (in-app plus WhatsApp); if not fixed by schedule time, fall back to creator self-posting with a pre-filled caption and verify by link |
| API publish fails | Retry with backoff; then fall back to self-post |
| Post deleted / archived / caption edited to remove disclosure during verification | Payout held; creator notified with 24h to restore; else dispute |
| Brand chargeback | Escrow covers the creator. Evidence pack (signed agreement, approvals, post proof) is generated automatically for the payment gateway |

---

## 7. Payments, escrow and payouts

- **Commercial structure (decided): the platform is the principal.** The brand buys the campaign from the platform, and the platform separately engages each creator. Because the platform collects its own revenue and pays its own suppliers (the creators), it doesn't need a marketplace split or escrow licence. "Escrow" becomes an internal ledger with a hold until verification ends.
  - Collections: Razorpay Payment Gateway (or Cashfree PG). Payouts: RazorpayX Payouts (or Cashfree Payouts).
  - Keep creator money in a separate current account ("creator payables") so it is never spent on operations.
- **Flow**:
  1. Brand pays the campaign price plus 18% GST at checkout (card/UPI/netbanking/invoice for enterprise), only for creators who accepted.
  2. Money sits in the creator-payables account; the ledger marks each slot's amount as "held".
  3. On `PAYOUT_RELEASED` (post verified live for 7 days), pay the creator their fee minus TDS to their verified bank account.
- **Why 7 days?** It covers the verification window and early-deletion risk. A **minimum live period (30 days suggested; 90 for premium)** is enforced by contract. Monitoring continues after payout, and a violation can be clawed back from future earnings or a small held reserve.
- **Tax (India; get it confirmed by a CA)**: 18% GST on the full campaign price charged to the brand. Creators registered for GST invoice the platform with GST, which the platform can claim as input credit. **TDS** on creator payments (likely section 194C for advertising work; confirm with CA), with automated Form 16A and an earnings statement.
- **Business model (decided): 50/50 split, not disclosed.** Brand price = creator fee ÷ (1 − margin), with the margin defaulting to 50%. Brands see only the price they pay. Creators see only the fee they receive. Rules that keep this safe:
  - Contracts and UI never state or imply that the creator gets the brand's full payment.
  - The margin is a setting (global and per campaign), so it can be tuned if brands or creators push back. 50% is well above the market norm of roughly 20-30%.
  - Brand and creator talk only through in-app chat with contact details masked, plus a non-circumvention clause.
- **Refund policy (automatic)**:
  - Before creator acceptance: 100%.
  - After acceptance, before content: 100% minus a small fee to the creator (cancellation compensation).
  - After content delivered: no refund (content is owned per licence) unless the content fails agreed checks.

---

## 8. Consent: how to automate it end to end

Consent should be **structured data, not just a PDF**. Build a **Consent Ledger** service.

### 8.1 Principles
1. **Granular**: separate consents for platform terms, data processing, Instagram data access, publishing on their behalf, AI script help, AI likeness use, digital-twin creation, marketing messages.
2. **Scoped**: likeness consent is **per campaign**, with a licence scope (channels, duration, territory, paid usage yes/no).
3. **Informed**: show a plain-language summary above the legal text ("The brand can use this Reel in their own ads for 3 months in India").
4. **Explicit and recorded**: every consent event is logged with user ID, document version and hash, timestamp, IP, device, method (clickwrap / OTP e-sign / Aadhaar eSign), and the exact asset hash it applies to.
5. **Revocable**: users can withdraw via a dashboard. Future use stops immediately; past licensed use follows the contract. Revoking the digital twin deletes the model.
6. **Compliant with data law**: India DPDP Act 2023 (notice, purpose limitation, consent manager-compatible, data deletion), GDPR if serving the EU. Also Meta Platform Terms (data use limited to the permissions granted).

### 8.2 The consent moments (all automated)
| Moment | Who | What is consented | Mechanism |
|---|---|---|---|
| Signup | Both | Terms, privacy notice, DPDP processing | Clickwrap, versioned |
| Instagram connect | Creator | Read insights; publish content (separate scope) | Meta OAuth scopes plus our in-app explanation |
| KYC | Both | Identity verification, tax use | OTP / DigiLocker consent |
| AI preferences | Creator | Mode A / B, digital twin (optional) | Toggle plus e-sign for likeness |
| Offer acceptance | Creator | **Campaign agreement**: deliverables, fee, timeline, usage rights, exclusivity, min live period, AI mode | OTP e-sign generated from template with campaign variables |
| Checkout | Brand | Campaign order, refund policy, auto-approve rule | Clickwrap plus payment |
| Final asset approval | Brand, then Creator | **This exact file (hash) and caption** may be published at this time | One-tap approve in app/WhatsApp, logged with asset hash |
| Usage-rights extension | Both | Extra paid ad usage beyond original term | New mini-agreement plus payment |
| Revocation | Creator | Withdraw likeness / publishing permission | Dashboard; triggers workflow |

### 8.3 Automation mechanics
- **Contract templates** with variables filled automatically from the campaign (a template engine producing a PDF). Every generated contract is hashed and stored immutably (S3 Object Lock / WORM).
- **E-sign**: OTP-based e-sign in-house for standard contracts (legally acceptable for most commercial contracts; get this confirmed by a lawyer), or an e-sign provider (Leegality, Digio, DocuSign) with Aadhaar eSign for higher-value deals.
- **Policy engine**: every action that needs consent (`publish`, `generate_with_likeness`, `use_in_paid_ads`) calls `consent.check(user, action, campaign, asset_hash)` and **fails closed** if there is no valid consent.
- **Audit export**: one click produces an evidence pack for disputes, chargebacks or regulators.

---

## 9. Instagram integration: facts and constraints to design around

- Use the **Instagram Graph API** content publishing endpoints (Business/Creator accounts only). Supports feed images, carousels, Reels and Stories. There is a **rolling 24-hour publishing cap per account** (check the current limit); track it.
- Access tokens are long-lived (~60 days) and must be **refreshed** automatically. Monitor for revoked permissions.
- The **Paid Partnership (branded content) label** and collab posts have limited or varying API support. Plan to:
  1. Always put the disclosure in the caption (`#ad`, `#sponsored` / "Paid partnership with @brand"), and
  2. Ask the creator to add the in-app partnership label, or use self-post mode when the label is required via app.
- **Meta App Review** is required for the publish and insights permissions. Expect it to take weeks and to need a screencast of the full flow. **Start this early**; it is the #1 launch blocker.
- Audio: API-published Reels can't use Instagram's licensed music library. Use royalty-free or brand-licensed audio baked into the video.
- Metrics after posting: pull media insights (reach, plays, likes, comments, saves, shares) daily during verification and for the report.
- Future platforms: YouTube Shorts (YouTube Data API upload), and possibly others once proven.

---

## 10. Trust, safety and anti-fraud

| Risk | Control |
|---|---|
| Fake followers / engagement pods | Authenticity scoring at onboarding plus monthly re-scan; anomaly detection on growth |
| Fake brands / scams targeting creators | Domain verification, business KYC, payment captured **before** creator starts work |
| Stolen cards / chargebacks | 3DS / UPI; escrow; evidence pack; velocity limits for new brands |
| Off-platform deals (disintermediation) | Value that's hard to replicate off-platform (escrow, auto-contracts, AI production, tax handling); in-app chat masks phone/email for first N campaigns; clause in terms |
| Harmful content / false claims | Automated pre-publish checks against the confirmed brief; restricted categories; human review queue for flagged items |
| Creator reputation damage | Creators see full brief before accepting; red-line categories; brand ratings visible to creators |
| Account takeover | 2FA, device binding for payout changes, cooldown plus alert on bank account change |
| Minors | 18+ only in v1, verified via KYC |
| Deepfake misuse | Likeness never used without per-asset approval; C2PA watermarking; twin models encrypted and scoped per creator |

---

## 11. Notifications and communication
- Channels: **WhatsApp Business API** (creators live on WhatsApp, especially in India), email, push, in-app.
- Every actionable notification has a **one-tap deep link** (accept offer, approve asset, reconnect Instagram).
- In-app chat per campaign (brand ⇄ creator ⇄ ops), moderated and logged.

---

## 12. Reporting and analytics
Brands, creators and ops each get a full dashboard: action items, status with the next step, performance vs prediction, money flow, content and usage rights, consent records, AI insights, and exportable reports. Full spec: **[DASHBOARDS.md](DASHBOARDS.md)**.

---

## 13. Technical architecture (suggested)

```
┌─────────────── Web (Next.js) / Mobile (React Native, later) ────────────────┐
│ Brand app · Creator app · Ops console                                        │
└───────────────▲──────────────────────────────────────────────────────────────┘
                │ REST/GraphQL (auth: JWT + RBAC)
┌───────────────┴─────────────── API (Node/NestJS or Python/FastAPI) ─────────┐
│ Accounts · Campaigns · Matching · Content · Consent Ledger · Payments ·      │
│ Notifications · Integrations (Meta, WhatsApp, Payments, KYC, e-sign)         │
└───────┬───────────────┬───────────────┬───────────────┬──────────────────────┘
        │               │               │               │
  PostgreSQL +     Workflow engine   Object storage   AI services
  pgvector         (Temporal /       (S3 + Object     • LLM (brief, claims, scripts,
  (core data,      BullMQ+Redis)     Lock for          explanations): Claude
   embeddings)     timers, retries   contracts)       • Vision (logo/product check)
                                                       • Image/Video gen (Mode B/C)
                                                       • C2PA signing
```

**Core entities**: `User`, `Organization(Brand)`, `CreatorProfile`, `SocialAccount`, `NicheTaxonomy`, `Campaign`, `ProductBrief(version)`, `Slot` (one creator deliverable), `Offer`, `Agreement`, `ConsentEvent`, `Asset(version, hash)`, `Approval`, `Post`, `MetricSnapshot`, `Payment`, `Payout`, `Dispute`, `AuditLog`.

**Engineering principles**
- Idempotent webhooks (payments, Meta); outbox pattern for events.
- Every state change is an event, which gives a full audit trail for free.
- Feature flags per content mode and per region.
- PII encrypted at rest (KYC, bank); secrets in a vault; least-privilege tokens.

---

## 14. Phased roadmap

| Phase | Duration (indicative) | Scope | Goal |
|---|---|---|---|
| **0: Concierge** | 3-4 wks | Landing page, Typeform onboarding, manual matching in a sheet, Razorpay links, creators post manually | Validate demand; 10 brands, 100 creators, 20 campaigns; learn pricing |
| **1: MVP** | 8-12 wks | Onboarding plus IG connect, KYC, AI brief from URL, rule-based matching plus scoring, offers, e-sign, escrow, **Mode A** with AI script assist, creator/brand approvals, API publish plus self-post fallback, 7-day verification, auto payout, basic reports. **Submit Meta App Review in week 1.** | Fully automated happy path |
| **2: AI production** | +8 wks | Mode C (brand AI UGC with avatars), AI editing for Mode A, usage-rights upsell, WhatsApp flows, Shopify attribution, learning-to-rank matching | Margin and speed |
| **3: Scale** | +12 wks | Mode B digital twins (opt-in), agencies, YouTube Shorts, performance-based pricing (bonus on results), mobile apps, multi-currency | Expand market |

---

## 15. KPIs
- Supply: approved creators by niche and tier; % with valid IG token.
- Demand: brands activated; time from signup to first paid campaign.
- Funnel: brief confirmed → shortlist → offer acceptance rate → paid → published → verified.
- Speed: median hours from payment to published post.
- Quality: brand repeat rate, creator NPS, revision rounds per asset, dispute rate (<2%), post-deletion rate.
- Matching: predicted vs actual engagement error; acceptance rate of top-3 picks.
- Unit economics: take rate, gross margin after AI generation and payment costs, CAC per side.

---

## 16. Risk register (top 10)
1. **Meta App Review rejection / API policy change**: apply early; always keep the self-post fallback; don't depend on a single platform long term.
2. **Likeness / deepfake liability**: Mode A default; per-asset approvals; legal review of likeness licence.
3. **Regulatory disclosure failures**: enforced disclosure in caption plus automatic checks during verification.
4. **Payment licensing**: use a licensed gateway's escrow/split product.
5. **Cold start (chicken and egg)**: seed supply in 3-4 niches first (e.g. beauty, fashion, food, fitness) and one geography; recruit nano and micro creators by hand.
6. **Fake-follower creators hurting brand results**: authenticity scoring; performance data feeds back into ranking.
7. **Disintermediation**: make the platform's value exceed the fee.
8. **AI content quality**: human-in-the-loop approvals; brand-safe templates; measure revision rate.
9. **Tax/TDS mistakes**: CA-reviewed logic; automated statements.
10. **Operational load from edge cases**: state machine with timeouts; ops console with a "stuck" queue.

---

## 17. Founder decisions (24 Sep 2026)
| # | Question | Decision | What it changes |
|---|---|---|---|
| 1 | Launch geography | **India first** | INR only, GST/TDS, Indian KYC (PAN, GSTIN, bank verification), Razorpay/Cashfree, WhatsApp as the main channel, DPDP Act |
| 2 | Launch niches | **All in-demand niches (15+ top-level categories with sub-niches)** | Full taxonomy from day 1. Matching must show "not enough creators in this niche yet" instead of weak matches. Supply-seeding tracks coverage per niche |
| 3 | Role of AI | **Speed/cost helper** | Mode A (creator-made, AI-assisted) is the headline. Mode C (AI avatars) is an add-on later |
| 4 | Paid-ads reuse (whitelisting) | **Yes, from day 1, in both contracts** | Usage rights for paid ads are a standard clause. The creator must also grant the brand partner access in the Instagram app, so the platform tracks and reminds |
| 5 | Pricing | **50/50 split of the campaign price, not disclosed** | Principal model, margin engine, strictly separated brand and creator views (see §7) |
| 6 | Creator tier | **Nano and micro (1k-100k followers)** | Authenticity checks matter more. Onboarding must be fully self-serve and mobile-first |
| 7 | Build | **Claude builds it** | Tech plan and task list: [TECH_PLAN.md](TECH_PLAN.md) |

---

*Not legal or tax advice. Before launch, have the creator agreement, brand agreement, likeness licence, privacy notice and tax flows reviewed by a lawyer and a chartered accountant in each launch market.*
