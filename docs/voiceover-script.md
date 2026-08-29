# Recover — demo voiceover

Narration for the demo video, written for the **1.5× cut** and rendered to MP3.

| file | what it is |
|---|---|
| `docs/demo-with-voiceover.mp4` | **the finished thing** — 1.5× video with narration, 7:11 |
| `docs/demo-recording.mp4` | the raw take, 10:40, no audio |
| `docs/demo-recording-1.5x.mp4` | sped up, no audio |
| `docs/voiceover.mp3` | one aligned track, 7:05 |
| `docs/voiceover/segments/S01.mp3` … | per segment, if you would rather place them by hand |
| `docs/voiceover/segments.json` | **source of truth** — the words and their offsets |
| `docs/voiceover/build-voiceover.py` | renders the audio from that JSON |

## Rebuilding after an edit

```bash
cd docs/voiceover
python3 build-voiceover.py                  # Samantha (default)
python3 build-voiceover.py --voice Rishi    # Indian English
python3 build-voiceover.py --list-voices
```

Then re-mux:

```bash
ffmpeg -i docs/demo-recording-1.5x.mp4 -i docs/voiceover.mp3 \
  -c:v copy -c:a aac -b:a 192k -map 0:v:0 -map 1:a:0 \
  -movflags +faststart -y docs/demo-with-voiceover.mp4
```

**Do not pass `-shortest`.** The narration ends five seconds before the picture
does, and `-shortest` cuts the closing shot to match it.

The builder refuses to finish quietly if a segment does not fit its window. It
first tries speaking faster, and if that would push past 205 wpm it tells you how
many words to cut instead — a segment that overruns talks over the next one, and
by the end the narration is describing a page that left the screen a minute ago.

## Timing

Windows are the measured segment windows from the 10:40 take, divided by 1.5.
Verified against the rendered track: speech begins within a tenth of a second of
every declared offset.

| seg | at | window | subject |
|---|---|---|---|
| S01 | 0:00 | 15.3s | the problem |
| S02 | 0:15 | 16.0s | multi-tenant sign-in |
| S03 | 0:31 | 18.7s | the funnel |
| S04 | 0:50 | 36.0s | causal diagnosis (DAG) |
| S05 | 1:26 | 23.3s | bandit, guardrail |
| S06 | 1:49 | 26.0s | churn, handoff, real link |
| S07 | 2:15 | 24.7s | playbooks, learned arms |
| S08 | 2:40 | 19.3s | tenant switch |
| S09 | 2:59 | 31.3s | generated message |
| S10 | 3:31 | 19.3s | the silent recovery |
| S11 | 3:50 | 15.3s | consent first |
| S12 | 4:05 | 25.3s | the learning curve |
| S13 | 4:31 | 20.0s | incremental ROI |
| S14 | 4:51 | 22.0s | the audit trail |
| S15 | 5:13 | 28.7s | the network effect |
| S16 | 5:41 | 20.7s | simulator and seeded data |
| S17 | 6:02 | 25.3s | real Razorpay, test mode |
| S18 | 6:27 | 33.3s | promise to pay |
| S19 | 7:01 | 10.0s | close |

Every segment is read at 165 wpm — deliberately unhurried, because the script
explains concepts rather than listing features, and there is no point explaining
something too fast to follow.

## How the jargon is handled

Each technical term is named and then immediately given in plain words, so a
reviewer who knows the field hears the right term and one who doesn't still
follows the argument.

| term | the plain gloss in the script |
|---|---|
| Causal graph / DAG | "it maps what causes what, so it can tell a bank outage apart from an empty account, instead of just correlating them" |
| Contextual bandit, Thompson sampling | "it keeps a probability curve for each option, and draws from it, so it explores while it's unsure and commits once it's confident" |
| Uplift modelling | "leave some customers alone, so you can prove what you caused" |
| Federated network intelligence | "no customer data leaves any account, only the rates" |
| Guardrails | named as RBI retry limits, TRAI quiet hours, consent |

The script also argues *why each mechanism earns its place*, which is the part a
judge is actually weighing:

- **The dip in the learning curve is explained, not hidden** — "exploration costs
  real recoveries. A policy that started ahead never had to learn."
- **Restraint is framed as the product** — Aditya gets no message, Sana gets no
  steps at all, and both are presented as the system working rather than as
  nothing happening.
- **Uplift is framed against the obvious objection** — gross recovery is called a
  vanity number before anyone else can call it that.
- **The handoff is framed as judgment** — "an agent that knows where its judgment
  ends is worth more than one that doesn't."

## What is claimed, and what the screen shows

The UI is honest about itself and the narration matches it:

- **The Razorpay link is real** — `plink_TVYrz70LbmyGkF`, test mode,
  `simulated: false`. S06 and S17 say so.
- **WhatsApp is simulated, and the case detail shows `"simulated": true`** beside
  the message. S09 says the message is *drafted* and *handed to the adapter*, and
  never says delivered. **Do not upgrade that wording** — a judge can read the
  contradiction on screen.
- **The classifications are real Gemini output** — `promise_to_pay` at 0.91,
  `churn_confirmation` at 0.93, both `is_stub: false`.
- **The seeded data is declared out loud** in S16, rather than left for someone to
  discover: three merchants, six personas, hundreds of historical cases with a
  real control group.
- **Sana's opt-out was never classified** — her case stopped at the consent gate
  before any step ran, and S11 is worded to match.

## Voice

Default is **Samantha** (macOS, en-US) — the clearest of the built-in voices.
`docs/voiceover/sample-Rishi.mp3` and `sample-Daniel.mp3` are the same line in
Indian and British English if you would rather.

These are system voices, not ElevenLabs. They are clear and correctly paced, but
flat next to a paid neural voice. If you want to upgrade, the per-segment text in
`segments.json` is what you paste in — keep the same `start` offsets and the
alignment still holds.
