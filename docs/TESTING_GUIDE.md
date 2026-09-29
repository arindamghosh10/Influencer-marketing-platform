# Testing guide (local)

Step-by-step scenarios to try every part of CreatorBridge on your own computer. Each one takes
5–15 minutes. Start the app as described in the README (`uv run python manage.py devserver`)
and open http://127.0.0.1:8000.

## Before you start

**Logins** (password for all: `demo-pass-123`)

| Who | Email |
|---|---|
| Brand | `brand@demo.local` |
| Ops (your team) | `ops@demo.local` |
| Creators | `creator000@demo.local` … `creator079@demo.local` |

**Which creator got the offer?** The number at the end of a creator's Instagram handle is their
login number. `@meera.suncare68` logs in as `creator068@demo.local`.

**Use two browser windows.** Keep the brand logged in a normal window and the creator (or ops)
in a private/incognito window, so you don't have to log out and in all the time.

**Nothing real happens locally:**
- Payments use a test button (no money moves).
- Instagram is simulated: "publishing" creates a fake post with fake but realistic stats.
- Emails (sign-in codes, notifications, weekly reports) are printed in the terminal running the
  server. Codes for signing agreements are also shown on the page.

**Skipping time.** Some steps normally wait for days (48h to answer an offer, 7 days of post
checks before a creator is paid). Log in as ops, open **Ops** (`/ops/`) and use
**Test: run as if [8] days passed → Run** (fractions work too, e.g. 1.75). This only exists while `DEBUG=true` (your local
`.env`). Keep in mind it also expires unanswered offers and auto-approves drafts that are
waiting for review, exactly as the real deadlines would.

**Starting over.** Stop the server, delete `db.sqlite3` (and the `media` folder if you like),
and run `devserver` again. It recreates and reseeds the database.

---

## 1. Happy path: brand launches a campaign, creator posts, creator gets paid

**Brand: create the campaign**
1. Log in as `brand@demo.local` → **+ New campaign**.
2. Name: `Sun launch`. Product notes: `SunShield SPF 50 gel sunscreen for oily skin, no white cast.`
   (You can also paste a real product page link; the brief is built from the page.)
3. Budget `200000`, number of creators `2`, keep the rest → save.
4. Check the brief (product, niches, topics). Try **Edit brief** if something looks wrong.
   Tick the claims box if shown → **Looks right: confirm and find creators**.
5. You see recommended creators with a match score, reasons and a price. Try **Remove** / **Add**
   and watch the selection box on the right update. → **Confirm selection** → **Send offers**.

   ✅ Check: prices shown to the brand are the brand prices. The creator's fee is never shown.

**Creator: accept**
6. On the campaign page, note the creator handles (for example `@meera.suncare68`). Log in as
   that creator (`creator068@demo.local`) in the other window.
7. Open the offer from the notification bell or the dashboard → **Accept: review and sign**.
   Type your name, get the code (shown on the page) and confirm.

   ✅ Check: the creator sees their own fee, which is lower than the price the brand sees.
   The difference is the platform margin and is never shown to either side.

**Brand: pay**
8. Back as the brand, refresh the campaign. **Ready to pay** shows the accepted creator(s) with
   GST. → **Review order and pay** → sign the order → **Pay … (test)**.
9. Open the invoice under **Invoices** (`CB/2026-27/00001`). CGST+SGST or IGST depends on the
   brand's state.

**Creator: make and submit the content**
10. As the creator, open the campaign workspace. Try the **AI script helper**.
11. Upload any short video or image. In the caption, include `#ad` (try once *without* it to see
    the automatic disclosure check complain) → **Send to brand**.

**Brand: review**
12. As the brand, open the creator from the campaign page → **Review draft**. Try
    **Request changes** with a comment first (the creator sees it and uploads a new version),
    then **Approve draft**.

**Creator: final OK and publish**
13. As the creator: pick a time a minute or two ahead → **Approve and schedule**. This stores the
    creator's consent tied to that exact file.
14. As ops: **Run scheduled jobs now**. The post goes "live" (simulated) and a link appears.

**Verification and payout**
15. As ops: **Test: run as if 8 days passed → Run**. The post passes its daily checks and
    the creator's payout becomes ready to pay.
16. Ops → **Payouts to send** → **Pay in admin**. Tick the payout, choose the action
    **Mark as paid**, enter any UTR (e.g. `UTR123`) → **Go**.

**See the results**
17. Brand: dashboard (spend, reach, views, chart), campaign page (results by creator),
    **Campaign report**, **Content library** (usage-rights expiry), **Billing**.
18. Creator: **Earnings** (monthly chart, payment with UTR) and the **financial-year statement**
    with TDS.

---

## 2. Creator declines → backup creator is offered automatically

1. Create and send a campaign as in steps 1–5 above.
2. Log in as one offered creator → **Decline** with a reason.
3. Refresh the brand's campaign page: the slot now shows a new creator ("Tried before: …").
   The brand is notified. Nothing to do.
4. Variation: don't answer at all, then as ops run **as if 3 days passed**. The offer expires and
   the backup is offered. The creator's reliability score drops.
5. Variation: when no backup fits the budget, the slot becomes **Unfilled** and the brand isn't
   charged for it.

## 3. Brand doesn't pay in time

1. Get a creator to accept (scenario 1, steps 1–7), but don't pay.
2. As ops, run **as if 6 days passed**. The acceptance is released and the slot goes to a
   backup creator.

## 4. Creator can't deliver → automatic refund with credit note

1. Complete scenario 1 up to payment (step 8).
2. As the creator, open the workspace → **Can't deliver this campaign?** → enter a reason → **Withdraw**.
3. Brand: **Billing** shows a credit note (`CB-CN/2026-27/00001`) and the net spend. Open it:
   it refers to the original invoice and reverses the GST.
4. Variation (ops cancels instead): `/admin/` → Offers → Slots → tick the slot → action
   **Cancel paid slot and refund the brand**, type a reason → **Go**.

   ✅ Check: after the brand approves a draft, withdrawal/cancel is no longer possible
   (a dispute is the way then).

## 5. Dispute → payout held → ops resolves

1. Get a post live (scenario 1 up to step 14).
2. Brand: open the creator's review page → **Report a problem** → pick a category, describe it →
   **Send report**. (A creator can do the same from their workspace.)
3. As ops, run **as if 8 days passed**. The post passes its checks, but the payout stays
   **on hold** because of the open dispute.
4. Ops → **Open disputes** → **Review**. The evidence pack shows the signed agreements, consents
   with file fingerprints, every draft and review, post checks and the full timeline.
5. Resolve with one of:
   - **Creator is paid in full**: payout released.
   - **Partial refund to brand, creator paid the rest**: enter the refund amount; the brand gets
     a credit note and the creator's payout is reduced to match.
   - **Brand refunded in full, creator not paid**: payout cancelled, post checks stop.
   - **No change**: the campaign continues as normal.
6. Both sides are notified. Check the brand's billing and the creator's earnings.

## 6. Add creators to a running campaign

1. Have a campaign with at least one paid creator (scenario 1 up to step 8).
2. Brand: campaign page → **Add creators**. Enter how many and the extra budget → **Find creators**.

   ✅ Check: creators already in this campaign are not in the list.
3. Adjust the selection → **Send offers**. The campaign budget increases by the extra budget,
   and new slots appear on the campaign page.
4. When a new creator accepts, **Ready to pay** shows only that creator, billed on a second
   invoice.
5. Variation: search, then **Discard** instead. Nothing is sent and the budget is unchanged.

## 7. Run a campaign again

1. Open a campaign whose posts went live (scenario 1).
2. **Run again** → a new campaign "… (repeat)" opens with the same settings and brief, already
   at the creator step.

   ✅ Check: creators who delivered last time are selected first, marked "Delivered your last
   campaign" (if they're still available and within budget).
3. Change the budget with **Edit settings** if you like, then continue as usual.

## 8. Onboarding a new creator and a new brand

1. Log out → **Sign up** as a creator with a new email. Complete the steps: profile, connect
   Instagram (simulated: any handle works), rates, content red lines, AI preference, KYC
   (test PAN such as `ABCPE1234F`, IFSC such as `HDFC0000123`), and sign the agreement.
   → **Submit for review**.
2. Ops: **Creators waiting for review** → **Review** → approve in admin. The creator can now
   be matched.
3. Same for a new brand: sign up as a brand, fill the profile (GSTIN is checksum-validated;
   `27AAPFU0939F1ZV` is a valid test value), sign, and have ops approve it. Until approved,
   the brand can build campaigns but can't send offers.

## 9. Sensitive products

1. Create a campaign for something like a weight-loss supplement or a personal loan app.
2. The brief flags the category and risky claims ("cures", "guaranteed"...).
   Blocked categories (tobacco/vaping, betting, adult, political) can't be confirmed at all.
3. For sensitive (not blocked) categories, offers wait for ops:
   `/admin/` → Campaigns → tick it → **Approve sensitive-category campaign** → **Go**.

## 10. Consent and privacy

- Creator or brand: **Consents** page in the menu shows every consent with its date, and
  optional ones can be withdrawn.
- Every signed agreement is stored with its exact text and a fingerprint (SHA-256); open it from
  the consents page.
- Ops: `/admin/` → Core → Events is the full audit log.

## 11. Reminders, Instagram health and the ops console

1. **Reminders:** send offers (scenario 1), then as ops run **as if 1.75 days passed**
   (42 hours: inside the last 12 hours of the 48-hour offer, but before it expires): each creator with an open offer gets
   "Your offer … expires in …" (bell and in the terminal as an email). Run it again: no
   duplicate. The same happens for brands before payment is due and before a draft is
   auto-approved.
2. **Instagram reconnect:** `/admin/` → Creators → open one → tick **Ig needs reconnect** → save.
   Log in as that creator: the dashboard asks them to reconnect, and they no longer appear in
   new matches. Reconnecting from the banner clears it.
3. **Ops console** (`/ops/`): the funnel (created → confirmed → offers → paid → live →
   completed) with GMV and margin, **Needs attention** (failed publishing, posts on hold,
   failed refunds, overdue payouts, creators who must reconnect, deletion requests) and
   **Integrations** (scheduler last run, AI, Instagram, payments).

## 12. Privacy and security

1. Footer → **Terms** and **Privacy** work without logging in.
2. Logged in → footer → **Your data** → **Download my data** gives a JSON file.

   ✅ Check: a creator's file has their fee but no brand prices; a brand's file has prices but
   no creator fees; no full PAN, bank number or Instagram token appears.
3. **Request deletion** → ops gets a notification and it shows under **Needs attention**.
   Ops closes it in `/admin/` → Core → Data requests.
4. Try logging in with a wrong password 6 times: the account is paused for 15 minutes
   ("Too many attempts"). Other accounts still work. (Restarting the server clears it.)

---

## Things to look out for (please note down anything odd)

- Any page that shows the **creator's fee to a brand** or the **brand's price to a creator**
  (this must never happen).
- Money that doesn't add up on invoices, credit notes, billing or earnings.
- Buttons that do nothing, confusing wording, or steps where you didn't know what to do next.
- Anything that looks broken on a phone-sized window.

## Automated tests

The same flows are covered by automated tests. Run them with:

```
uv run pytest -q
```
