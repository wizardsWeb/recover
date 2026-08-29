# Recover — demo voiceover

Narration for `frontend/tests/e2e/demo-recording.spec.ts`. Segment numbers match
the `S1 ·`, `S2 ·` … labels in that file exactly.

**Timings below are measured, not estimated.** They come from a passing run
against a local production build with the cursor and eased motion in place:
6:41 of video, 46 beats, every selector matched. (It grew from 6:08 because
typing a field takes longer than assigning its value, and an eased scroll takes
longer than a jump — both on purpose.) Re-run and re-read the `SEGMENT WINDOWS` table if you re-record —
navigation time moves, and it moves the windows with it.

## How to use this

1. Start the stack: backend on `:8000`, then `cd frontend && npm run build && npx next start`
2. Record: `npx playwright test --project=demo`
3. Read the `SEGMENT WINDOWS` table it prints. Those offsets are the truth.
4. Render one TTS file per segment, then lay each against the video at its offset.

**Per-segment files, not one long take.** The windows shift a second or two per
run, and the shift lands *between* segments rather than inside them. Eighteen
short files can each be nudged. One continuous take drifts and can only be fixed
by re-cutting.

## Reading notes for TTS

- `/` is a breath. `//` is a full stop's worth of pause.
- `[brackets]` is direction. Never read aloud.
- Numbers are written as they should be spoken. TTS reads `₹1,45,000` badly.
- Pace is ~2.4 words/second. Each segment gives its word budget; check a take
  fits before syncing.

## What is real, and what the screen admits

Worth knowing before you record narration over it, because the UI is honest and
the voiceover must not contradict it:

- **The Razorpay payment link is real.** `plink_TVYrz70LbmyGkF`, test mode,
  `simulated: false` on the execution row. Segment 6 says so.
- **WhatsApp is simulated, and the screen says so.** The case detail shows the
  adapter as `whatsapp_business_simulated` and `"simulated": true` in the raw
  JSON, right next to the message. Segments 9 and 16 therefore say the message is
  *drafted* and *handed to* the adapter. They never say delivered. **Do not
  upgrade that wording** — a judge can read the contradiction on screen.
- **The reply classifications are real Gemini output.** Meera's is
  `promise_to_pay` at 0.91 confidence, Vikram's `churn_confirmation` at 0.93,
  both `is_stub: false`, both Hinglish.
- **The network benchmark has no peer comparison yet.** The page says as much:
  *"With 2 other merchants on the network, a median would just be someone else's
  recovery rate with a different name on it."* Segment 15 talks about pooled
  rates and the outage, not about benchmarking against peers.

---

## SEGMENT 1 · 0:00–0:16 · 16s · landing page

*Landing hero, then two scrolls.*

> Every business taking payments online loses money to failures it never sees. /
> A card declines. A mandate lapses. A cart dies at the last step. // Most teams
> answer with one reminder, sent to everybody.

**31 words.**

---

## SEGMENT 2 · 0:16–0:36 · 20s · sign-up, then sign in

*Sign-up form, then signing in as Zenith Learning.*

> Recover answers differently. / It works out *why* each payment failed — / then
> decides whether contacting that customer helps at all. // It's multi-tenant.
> I'll sign in as Zenith Learning, an edtech business selling course
> subscriptions.

**36 words.**

---

## SEGMENT 3 · 0:36–0:56 · 20s · the dashboard

*Dashboard KPIs, recovery funnel, recent cases.*

> This is what the agent has been doing. // Not messages sent — a funnel. / How
> many payments failed, how many were worth acting on, how many came back. //
> That last number is the only one that pays for anything. / And most recovery
> tools can't tell you it, / because they never held anyone back to compare
> against.

**48 words.** *[Longest single hold in this segment is the funnel — land "worth
acting on" while it's on screen.]*

---

## SEGMENT 4 · 0:56–1:26 · 30s · S1 Suresh — causal diagnosis

*Suresh Iyer's case, `diagnose` expanded, the causal reasoning panel, competing
hypotheses.*

> Suresh Iyer. / Two thousand nine hundred and ninety-nine rupees, a subscription
> renewal, failed. // The agent doesn't guess at why. / It builds a causal graph
> over what it can actually observe — the hour, the bank, the instrument, his own
> history, and how the network is behaving — / and it returns a root cause: / a
> salary cycle mismatch, with a competing E-M-I taking the money first. //
> And then the part that matters most. / It shows you what else it considered, /
> and how confident it was in each one. // A diagnosis you can argue with is a
> diagnosis you can trust.

**72 words.** *[Densest segment. If a take runs long, cut the observables list
first — "the hour, the bank, the instrument".]*

---

## SEGMENT 5 · 1:26–1:54 · 28s · the bandit, uplift, guardrail

*`decide` and its alternatives fan, then `uplift check`, then `guardrail`.*

> Knowing the cause isn't knowing what to do. // A contextual bandit picks the
> action. / Thompson sampling, one posterior per context bucket — / here it's
> I-C-I-C-I, U-P-I, morning, high value. // It chose to retry on the date his
> salary actually lands, with a WhatsApp fallback. / These are the arms it passed
> over. //
> Then two gates before anything happens. / Would contacting him change the
> outcome at all? / And is this contact even allowed — R-B-I retry limits, T-R-A-I
> quiet hours, his own consent.

**65 words.**

---

## SEGMENT 6 · 1:54–2:28 · 34s · S5 Vikram — reply, handoff, real link

*Vikram Sethi's case, `listen`, `execute` with the payment link, the handoff card
inside it.*

> Vikram Sethi replied. / In Hinglish: "bhaisaab, beta ab coaching nahi le raha,
> cancel kar do please." // Gemini classified that — / churn confirmation,
> ninety-three per cent confidence. // This isn't a payment problem. It's a
> cancellation. //
> So the agent stopped chasing. / It had already generated a real Razorpay payment
> link — that's a live test-mode link, not a mock — / and then it handed the case
> to a human. // Retention isn't a retry. / An agent that knows where its judgment
> ends is worth more than one that doesn't.

**74 words.**

---

## SEGMENT 7 · 2:28–2:50 · 22s · tenant switch

*Signing out, signing in as Kajal & Co.*

> Different business. Same agent. // Signing out, signing back in as Kajal and
> Company — a direct-to-consumer beauty brand. //
> Different customers. Different playbook. / And a policy that learned on its own
> traffic, not on somebody else's. // Every merchant on this platform gets their
> own posterior. / Nobody inherits somebody else's mistakes.

**53 words.** *[The window covers a real sign-out and sign-in, so there is natural
quiet in the middle. Let it breathe rather than filling it.]*

---

## SEGMENT 8 · 2:50–2:59 · 9s · cases list

*Cases list with the uplift column.*

> Every case, with the column most dashboards don't have: / whether contact was
> going to help.

**22 words.**

---

## SEGMENT 9 · 2:59–3:25 · 26s · S2 Priya — the generated message

*Priya Menon's case, `execute` expanded with the drafted message, then `decide`.*

> Priya Menon abandoned a cart worth one thousand two hundred and forty rupees. /
> Root cause: price sensitivity at checkout. // Gemini drafts the message — / her
> language, the brand's voice, an eight per cent offer — / and hands it to the
> WhatsApp adapter. //
> That discount isn't a default that goes to everyone. / It's the arm the bandit
> chose, for her bucket, / against the arms it didn't.

**62 words.**

---

## SEGMENT 10 · 3:25–3:44 · 19s · S3 Aditya — the silent recovery

*Aditya Rao's case, `uplift check` expanded.*

> Aditya Rao's payment failed too. / But the cause was a transient issuer error —
> / and a retry fixes that on its own. // So nobody messaged him. / Eight hundred
> and forty rupees, recovered in silence. // The best recovery message is often
> the one you don't send.

**43 words.**

---

## SEGMENT 11 · 3:44–3:58 · 14s · S6 Sana — consent

*Sana Khatri's case. No step is expanded — there are none.*

> Sana Khatri had opted out. // So look at this case: / there are no steps. Not
> one. / The consent check ran before the agent chose anything at all, / and then
> it chose nothing. // Six hundred and eighty rupees, left alone.

**34 words.** *[Accuracy note: her case stopped at the consent gate before any
step ran. Do not say the opt-out was "processed in seconds" here — that number
belongs to segment 17, where the batch data supports it.]*

---

## SEGMENT 12 · 3:58–4:13 · 15s · playbooks

*Playbooks list, then the checkout-abandonment playbook.*

> Four playbooks. / Failed payments, abandoned checkouts, subscription failures,
> overdue invoices. // Each carries its own arms and its own limits. / The merchant
> sets the limits. The agent learns inside them.

**36 words.**

---

## SEGMENT 13 · 4:13–4:30 · 17s · B1 — the learning curve

*The batch page and its learning curve.*

> Does any of this actually beat a fixed rule? // Two hundred cases, both
> policies, the same customers. // The bandit overtakes the baseline at case
> fifty, / and settles at thirty-six per cent against twenty-six. // That gap is
> what a static rule leaves behind.

**43 words.**

---

## SEGMENT 14 · 4:30–4:50 · 20s · B2 — uplift ROI

*ROI page, then the uplift buckets.*

> Twelve lakh forty thousand rupees recovered. // But gross recovery is a vanity
> number. / Some of those customers would have paid anyway. //
> Against a held-out control group, the agent's real contribution is eight lakh
> eighty-five thousand rupees. / That's the incremental figure — / and it comes
> from splitting customers four ways. / Persuadable, sure thing, lost cause, do
> not disturb. // Only the first one is worth a message.

**48 words.** *[Cut "Persuadable, sure thing, lost cause, do not disturb" if long
— the screen shows all four.]*

---

## SEGMENT 15 · 4:50–5:37 · 47s · B3 — the network, live

*Network page, bank-by-hour heatmap, then a live SBI UPI outage after a reload.*

> Here's the thing one merchant can never do alone. // No single business sees
> enough failed payments to know whether a bank is actually down, / or whether it
> was just unlucky. // Across the network, everyone sees it. / Five banks,
> twenty-four hours, success rates pooled — / no customer data leaves anyone's
> account. Just the rates. //
> Green is healthy. Brown is degraded. Red is failing. / You can read a bank's
> whole day off one row. //
> And this is live, right now. / S-B-I's U-P-I stack has dropped to thirty-one per
> cent, against a normal of eighty-two. / Three merchants affected. Detected four
> seconds ago. //
> So every agent on the network stops retrying into it. / Immediately. / Before
> those retries fail and spend a customer's patience on a problem that was never
> theirs. // A failed retry costs trust you don't get back. / This is how you
> avoid spending it.

**121 words.** *[Longest window in the video, and the strongest moment. The
outage banner appears on a page reload part-way through — land "this is live,
right now" on it.]*

---

## SEGMENT 16 · 5:37–6:11 · 34s · S4 Meera — B2B promise to pay

*Signing in as Sharma Distributors, Meera Patil's case, `execute` with two
attempts, then `listen` with the promise card.*

> Third business. Different problem entirely. // Sharma Distributors,
> business-to-business. / One lakh forty-five thousand rupees, overdue. //
> No discount codes here. A graduated sequence — polite first, firmer second. /
> Two attempts, both logged. //
> Then Meera replied: "boss, fifty per cent abhi kar deti hoon, baaki twenty-five
> tak." // Gemini read that as a promise to pay. / Half now, the rest by the
> twenty-fifth. Ninety-one per cent confidence. //
> And the agent stood down. / Recovery is paused until the promised date. / It
> isn't chasing her, / because she already answered.

**79 words.**

---

## SEGMENT 17 · 6:11–6:35 · 24s · audit trail and test mode

*Audit log, then Settings, then the Test mode tab.*

> Every decision is here. / Which step, which actor, which case, what time. // Not
> a log of messages — a log of reasoning. //
> Across two hundred cases: / zero R-B-I violations. Zero T-R-A-I violations. /
> Fifteen retries blocked and seventeen messages held back, / because the rules
> said so. / Two opt-outs, both honoured. Four cases escalated to a human. //
> And it's all running on real Razorpay test credentials.

**55 words.** *[Accuracy note: the Playbooks, Compliance and Team tabs are
deliberately disabled placeholders. Do not describe a compliance settings
screen — the numbers above come from the audit log and the batch summary.]*

---

## SEGMENT 18 · 6:35–6:41 · 6s · close

*Back to the dashboard.*

> Find the cause. / Decide if contact helps. / Prove what it earned. // That's
> Recover.

**14 words.**

---

## Totals

**~1,010 words across 6:41.** That's 2.5 words a second — a comfortable read, with
the tight spots at segments 4, 15 and 16.

## If you need it under five minutes

The video is 6:41, not the 4:30–5:00 originally targeted. About 1:50 of it is
navigation, typing and eased scrolling between beats, and three of those navigations are sign-ins — which are
the multi-tenancy story, so they earn their time.

Cheapest cuts, in order, none of which lose a persona or an AI feature:

| Cut | Saves | Costs |
|---|---|---|
| Segment 12 (playbooks) | ~15s | the four-playbook overview |
| Segment 17's settings tail | ~11s | the test-mode credentials beat |
| Segment 1's second scroll | ~8s | one landing-page beat |
| Film Meera under Kajal's login | ~20s | the third tenant, and the B2B framing |

The first three together get you to about 6:05. Only the fourth breaks 5:00, and
it costs the most.
