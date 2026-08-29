# Recover — demo voiceover

Narration for `frontend/tests/e2e/demo-recording.spec.ts`. Segment numbers match
the `S1 ·`, `S2 ·` … labels in that file exactly.

**Timings are measured, not estimated.** From the passing take: **10:40**, 48
beats, every selector resolved, every page scrolled to the bottom. Re-run and
re-read the `SEGMENT WINDOWS` table if you re-record.

## How to use this

1. Backend on `:8000`; then `cd frontend && npm run build && npx next start`
2. **Pre-flight:** `npx playwright test selector-check --project=demo` (80s)
3. Record: `npm run demo:record` (25 fps) or `npm run demo:capture` (60 fps)
4. Read the `SEGMENT WINDOWS` table it prints — those offsets are the truth
5. Render one TTS file per segment, then lay each against the video at its offset

**Per-segment files, not one long take.** The windows shift a second or two per
run, and the shift lands *between* segments rather than inside them. Nineteen
short files can each be nudged. One continuous take drifts and can only be fixed
by re-cutting.

## Reading notes for TTS

- `/` is a breath. `//` is a full stop's worth of pause.
- `[brackets]` is direction. Never read aloud.
- Numbers are written as they should be spoken. TTS reads `₹1,45,000` badly.
- Pace is ~2.4 words/second. Each segment gives its budget; check a take fits
  before syncing.
- Every segment here is **under** its window. The pages scroll while you talk, so
  the spare seconds are deliberate — they are where the viewer reads the screen.

## What is real, and what the screen admits

The UI is honest about itself, and the narration must not contradict what a judge
can read on screen:

- **The Razorpay payment link is real.** `plink_TVYrz70LbmyGkF`, test mode,
  `simulated: false` on the execution row. Segment 6 says so.
- **WhatsApp is simulated, and the case detail says so** — it renders the adapter
  as `whatsapp_business_simulated` with `"simulated": true` in the raw JSON, right
  beside the message. Segments 9 and 18 therefore say the message is *drafted* and
  *handed to* the adapter. They never say delivered. **Do not upgrade that
  wording.**
- **The reply classifications are real Gemini output.** Meera's is
  `promise_to_pay` at 0.91 confidence, Vikram's `churn_confirmation` at 0.93 —
  both `is_stub: false`, both Hinglish.
- **The network benchmark has no peer comparison yet.** The page says so itself.
  Segment 15 talks about pooled rates and the outage, not about ranking.
- **Sana's opt-out was never classified.** Her case stopped at the consent gate
  before any step ran. Segment 11 is worded to match.

---

## SEGMENT 1 · 0:00–0:23 · 23s · the landing page

*Hero, then a full scroll through the pitch.*

> Every business taking payments online loses money to failures it never sees. /
> A card declines. A mandate lapses. A cart dies at the last step. //
> The usual answer is a reminder — the same one, sent to everybody who failed. //
> Recover does something different. / It works out *why* each payment failed, /
> and then decides whether contacting that customer helps at all. // Sometimes
> the answer is no. That turns out to matter more than anything else here.

**63 words.**

---

## SEGMENT 2 · 0:23–0:47 · 24s · sign-up, then sign in

*Clicks through to sign-up, back to sign in, types credentials, signs in.*

> It's a real multi-tenant product. / Sign up and you get your own workspace,
> your own customers, your own learned policy. //
> I'll sign in as Zenith Learning — / an edtech business selling course
> subscriptions, / where the thing that breaks is the monthly mandate.

**48 words.** *[There's a real sign-in here — typing, then a page load. Let the
last line land as the dashboard appears.]*

---

## SEGMENT 3 · 0:47–1:15 · 28s · the dashboard

*KPI tiles, then a full scroll to the funnel and recent cases.*

> This is what the agent has been doing. // Not a count of messages sent — a
> funnel. / How many payments failed. / How many the agent judged worth acting
> on. / How many actually came back. //
> That third number is the only one that pays for anything. // And most recovery
> tools genuinely cannot tell you it, / because they never held a group back to
> compare against. / If you message everybody, you can never know who would have
> paid anyway.

**77 words.**

---

## SEGMENT 4 · 1:15–2:09 · 54s · the cases list, then Suresh's diagnosis

*Cases table, scrolled. Then Suresh Iyer's case, scrolled, with `diagnose` and
`uplift check` expanded.*

> Every case the agent has opened, / with a column most dashboards don't have: /
> whether contact was going to help at all. //
> Suresh Iyer. Two thousand nine hundred and ninety-nine rupees. A subscription
> renewal that failed. //
> The agent doesn't guess at why. / It builds a causal graph over what it can
> actually observe — / the hour, the bank, the instrument, his own payment
> history, and how the whole network is behaving right now — / and it returns a
> root cause. //
> A salary cycle mismatch, / with a competing E-M-I taking the money first. // He
> isn't short of money. He's short of money *on the first of the month*. //
> And here's the part that matters most: / it shows you what else it considered,
> and how confident it was in each one. / A diagnosis you can argue with is a
> diagnosis you can trust. //
> Then the second question. / Would contacting him change the outcome — / or would
> he have paid regardless?

**126 words.** *[The longest window in the video. If a take runs long, cut the
observables list — "the hour, the bank, the instrument" — first.]*

---

## SEGMENT 5 · 2:09–2:44 · 35s · the bandit and the guardrail

*`decide` with its alternatives fan, then `guardrail`, then `execute`.*

> Knowing the cause still isn't knowing what to do. //
> A contextual bandit picks the action. / Thompson sampling, one posterior per
> context bucket — / here it's I-C-I-C-I, U-P-I, morning, high value. //
> It chose to retry on the date his salary actually lands, with a WhatsApp
> fallback. / And these are the arms it passed over, with the confidence it had
> in each. //
> Then two gates, before anything happens at all. / Is this contact allowed —
> R-B-I retry limits, T-R-A-I quiet hours, his own consent. // Only then does it
> act.

**82 words.**

---

## SEGMENT 6 · 2:44–3:23 · 39s · Vikram — churn, handoff, a real link

*Vikram Sethi's case: `listen`, then `execute` with the payment link and the
handoff card, then a full scroll.*

> Vikram Sethi replied. / In Hinglish: / "bhaisaab, beta ab coaching nahi le
> raha, cancel kar do please." //
> Gemini read that correctly. / Churn confirmation. Ninety-three per cent
> confidence. // This is not a payment problem. It's a cancellation. //
> So the agent stopped chasing him. / It had already generated a real Razorpay
> payment link — / a live test-mode link, not a mock — / and then it handed the
> case to a human, with the context attached. //
> Retention isn't a retry. / An agent that knows where its own judgment ends is
> worth more than one that doesn't.

**93 words.**

---

## SEGMENT 7 · 3:23–4:00 · 37s · playbooks, and inside one

*Playbooks list, then the checkout-abandonment playbook, scrolled through its arm
table and limits.*

> Four playbooks. / Failed payments, abandoned checkouts, subscription failures,
> overdue invoices. //
> And inside one, everything it has learned. / Every arm, its win rate, how many
> times it's been tried, / and the ninety-five per cent interval around each. //
> "WhatsApp saved cart, eight per cent" is winning at seventy-three. / Twelve per
> cent does *worse* — a bigger discount, fewer recoveries. // That's not
> something you would have guessed. It's something you measure. //
> And the merchant sets the limits: / one message a day, three a week, a fifteen
> per cent discount cap. / The agent learns inside them, / never around them.

**101 words.**

---

## SEGMENT 8 · 4:00–4:29 · 29s · tenant switch

*Signs out through the account menu, signs in as Kajal & Co.*

> Different business. Same agent. //
> Kajal and Company — a direct-to-consumer beauty brand. / Different customers,
> a different playbook, / and a policy that learned on its own traffic rather
> than somebody else's. //
> Every merchant gets their own posterior. / Nobody inherits anyone else's
> mistakes, / and nobody's data leaves their account.

**55 words.** *[Covers a real sign-out and sign-in — there is natural quiet in
the middle. Let it sit.]*

---

## SEGMENT 9 · 4:29–5:16 · 47s · Priya — the generated message

*Kajal's cases, scrolled. Then Priya Menon's case with `execute` and `decide`.*

> Kajal's cases. Same agent, completely different failure shapes. //
> Priya Menon abandoned a cart worth one thousand two hundred and forty rupees. /
> Root cause: price sensitivity at checkout. //
> Gemini drafts the message. / Her language, the brand's voice, / and an eight per
> cent offer — and hands it to the WhatsApp adapter. //
> Read it. It's Hinglish, because that's how she writes. / It names the product.
> It doesn't beg. //
> And that discount is not a default that goes to everybody. / It's the arm the
> bandit chose for her bucket, / measured against the arms it didn't choose. //
> The agent is deciding how much margin to give away, / customer by customer.

**110 words.**

---

## SEGMENT 10 · 5:16–5:45 · 29s · Aditya — the silent recovery

*Aditya Rao's case: `diagnose`, then `execute`.*

> Aditya Rao's payment failed too. / But the cause was a transient issuer error —
> / the bank simply dropped it. //
> A retry fixes that on its own. // So nobody messaged him. / No discount. No
> WhatsApp. Nothing. / Eight hundred and forty rupees, recovered in silence. //
> The best recovery message is very often the one you never send. / That's margin
> the agent didn't spend and goodwill it didn't burn.

**71 words.**

---

## SEGMENT 11 · 5:45–6:08 · 23s · Sana — consent

*Sana Khatri's case, scrolled. No step is expanded — there are none.*

> Sana Khatri had opted out. //
> So look at her case. / There are no steps. Not one. //
> The consent check ran before the agent chose anything at all — / and then it
> chose nothing. / Six hundred and eighty rupees, deliberately left alone. //
> Compliance here isn't a filter at the end. It's the first gate.

**58 words.**

---

## SEGMENT 12 · 6:08–6:46 · 38s · the learning curve

*Batch page, hovering the chart, then scrolled to the compliance summary.*

> Does any of this actually beat a fixed rule? //
> Two hundred cases. Both policies. The same customers. //
> The bandit *loses* early — you can see it dip — / because exploration costs
> real recoveries. / A policy that started ahead would be one that never had to
> learn anything. //
> It overtakes at case fifty, / and settles at thirty-six per cent against
> twenty-six. //
> And underneath: / zero R-B-I violations. Zero T-R-A-I violations. / Fifteen
> retries blocked and seventeen messages held back, because the rules said so. /
> Two opt-outs, both honoured.

**89 words.**

---

## SEGMENT 13 · 6:46–7:16 · 30s · uplift ROI

*ROI page, scrolled through to the uplift buckets.*

> Twelve lakh forty thousand rupees recovered. //
> But gross recovery is a vanity number. / Some of those customers would have
> paid anyway. //
> Against a held-out control group, the agent's real contribution is / eight lakh
> eighty-five thousand. // That's the incremental figure — / seventy-one per cent
> of the gross, and the only number worth defending. //
> It comes from splitting customers four ways: / persuadable, sure thing, lost
> cause, do not disturb. / Only the first group is worth a message.

**79 words.**

---

## SEGMENT 14 · 7:16–7:49 · 33s · the audit trail

*Audit log, scrolled.*

> Every decision the agent made is here. / Which step. Which actor. Which case.
> What time. //
> This is not a log of messages. It's a log of *reasoning*. // You can take any
> outcome and walk backwards to the evidence that produced it. //
> Which matters, because "the model decided" is not an answer you can give a
> regulator, / or a merchant asking why their customer got a discount and the one
> beside them didn't.

**77 words.**

---

## SEGMENT 15 · 7:49–8:32 · 43s · the network, and a live outage

*Network page, scrolled through the heatmap and insights, then the SBI UPI
downtime button is clicked and the banner appears.*

> Here's the thing one merchant can never do alone. //
> No single business sees enough failed payments to know whether a bank is
> actually down, / or whether it was just unlucky. / Across the network, everyone
> sees it. //
> Five banks. Twenty-four hours. Success rates pooled. / No customer data leaves
> anyone's account — just the rates. // Green is healthy, brown is degraded, red
> is failing. You can read a bank's whole day off one row. //
> Now watch. // S-B-I's U-P-I stack drops to thirty-one per cent, against a
> normal of eighty-two. / Detected in seconds. Three merchants affected. //
> And every agent on the network stops retrying into it. / Immediately. / Before
> those retries fail and spend a customer's patience on a problem that was never
> theirs.

**114 words.** *[The strongest moment. Land "now watch" just before the click,
and "drops to thirty-one per cent" as the red banner appears.]*

---

## SEGMENT 16 · 8:32–9:03 · 31s · the simulator

*Simulator page, scrolled through fixtures, event stream, scenario runner, reply
injector.*

> One more thing, and it's the honest one. //
> Everything you've just watched came from here. / A simulator that manufactures
> the payment events a real Razorpay account would send. //
> Nine scripted scenarios. / A reply injector that puts a Hinglish message into a
> live case as if it had arrived on WhatsApp. / A live event stream. //
> It exists because you cannot wait for real customers to fail on cue — / and it's
> locked to development environments, / because a thing that manufactures
> financial events has no business existing in production.

**86 words.**

---

## SEGMENT 17 · 9:03–9:41 · 38s · settings and test mode

*Settings, then the Test mode tab, scrolled.*

> And it is wired to a real Razorpay account, in test mode. //
> Real keys. Real payment links — the one in Vikram's case is live, you could open
> it. / Real webhooks coming back. //
> Nothing here is a screenshot or a mock. / The payment rail is genuinely
> connected; / it's the customers who are synthetic, / and only because real ones
> don't fail on a schedule that suits a demo. //
> Which is the whole point of the simulator: / the agent cannot tell the
> difference, / so what you've seen it do is what it does.

**94 words.**

---

## SEGMENT 18 · 9:41–10:31 · 50s · Sharma — B2B promise to pay

*Signs in as Sharma Distributors, opens Meera Patil's case, expands `execute`
then `listen`, then scrolls.*

> Third business. Completely different problem. //
> Sharma Distributors. Business to business. / One lakh forty-five thousand
> rupees, overdue. //
> No discount codes here — that would be insulting, and it wouldn't work. / A
> graduated sequence instead. Polite first. Firmer second. / Two attempts, both
> logged. //
> Then Meera replied. / "boss, fifty per cent abhi kar deti hoon, baaki
> twenty-five tak." //
> Gemini read it as a promise to pay. / Half now, the rest by the twenty-fifth.
> Ninety-one per cent confidence. //
> And the agent stood down. / Recovery paused until the promised date. / It is not
> chasing her, / because she already answered. //
> A human collections agent would do exactly that. / Most software would send the
> next reminder on schedule / and lose the relationship over a fortnight.

**122 words.**

---

## SEGMENT 19 · 10:31–10:40 · 9s · close

*Back to the dashboard.*

> Find the cause. / Decide if contact helps. / Prove what it earned. // That's
> Recover.

**15 words.**

---

## Totals

**~1,510 words across 10:40** — about 2.4 words a second, with the tightest reads
at segments 4, 15 and 18.

## The length, honestly

10:40 is well past the five minutes buildathon judges usually watch. It is that
long because it now does everything asked of it: thirteen pages, six personas,
three tenants, every page scrolled to the bottom, and every navigation a real
click rather than a URL edit. Roughly three and a half minutes of it is scrolling
and page transitions.

If you want a shorter cut, take it from the ends rather than the middle — the
persona beats are the substance:

| Cut | Saves | Costs |
|---|---|---|
| Segment 16 (simulator) | ~31s | the "here's how it was made" beat |
| Segment 17 (test mode) | ~38s | the "real Razorpay" claim |
| Segment 7's playbook detail | ~20s | the arm posterior table |
| Segment 14 (audit) | ~33s | the compliance story's evidence |
| Segment 10 or 11 (Aditya or Sana) | ~25s | one of the two restraint beats |

Dropping 16, 17 and half of 7 lands near **9:10**. Getting under five minutes
means dropping a tenant, and at that point it is a different video — better to
cut a second, shorter edit from this footage than to re-record.
