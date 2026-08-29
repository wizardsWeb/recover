/**
 * The demo recording.
 *
 * One test, run start to finish, producing a single .webm. Segment numbers here
 * match `docs/voiceover-script.md` exactly — segment 7 in this file is segment 7
 * in that file, and the `beat()` durations are the seconds the narration for
 * that segment has to fill. Change a duration here and change it there.
 *
 * **No `page.pause()`.** It is a debugging tool: it opens the Playwright
 * Inspector and blocks until a human clicks resume, which in a recording means a
 * frozen video with a devtools window in it. Pacing comes from `beat()`.
 *
 * **Where the data comes from.** `backend/scripts/demo_state.json`, written by
 * `backend/scripts/prepare_demo.py`. Case ids are read from it rather than
 * hardcoded, because re-running the seeder issues new ones.
 *
 * **What this asserts.** Only that the page it is about to film actually
 * rendered. It is not a test of the product; a failed assertion here means the
 * narration would be talking over an empty div, which is worth stopping for.
 * Bandit arms are deliberately not asserted — the arm is a Thompson draw and
 * varies per seeding run, so `demo_state.json` records what was actually chosen.
 *
 * Run it:
 *
 *     cd frontend
 *     npx playwright test --project=demo
 *
 * Against a local stack instead of the deployment (see the batch segment for why
 * you might want to):
 *
 *     DEMO_BASE_URL=http://localhost:3000 npx playwright test --project=demo
 *
 * The video lands in `tests/e2e/recordings/` as a .webm. Convert for editing:
 *
 *     ffmpeg -i recording.webm -c:v libx264 -crf 18 -pix_fmt yuv420p recording.mp4
 */

import { expect, test, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

import {
  click,
  installCursor,
  moveTo,
  scrollBy,
  scrollToLocator,
  settleCursor,
  type as typeInto,
} from "./lib/cinematics";

interface DemoCase {
  case_id: string;
  merchant: string;
  customer_name: string;
  expected_arm: string;
  expected_status: string;
  actual_arm: string;
  actual_status: string;
}

interface DemoState {
  base_url: string;
  accounts: Record<
    string,
    { email: string; password: string; merchant_id: string; brand_name: string }
  >;
  cases: Record<string, DemoCase>;
  batch_id: string;
  network_alert_id: string;
  generated_at: string;
}

const state: DemoState = JSON.parse(
  fs.readFileSync(
    path.resolve(__dirname, "../../../backend/scripts/demo_state.json"),
    "utf8",
  ),
);

/** Wall clock at the first beat, which is roughly when the video starts. */
let startedAt = 0;

/** One row per beat: where it actually landed in the video, and how long it held. */
const timeline: { at: number; hold: number; label: string }[] = [];

const mmss = (s: number) =>
  `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`;

/**
 * Hold still for `seconds` so the narration for this beat has room.
 *
 * The offset logged here is **real elapsed time**, not the sum of the holds
 * before it. Those two numbers are not the same and the difference is not small:
 * every navigation in between costs seconds the holds never accounted for, and
 * against a deployment a region away that adds up to a minute or more across the
 * run. A voiceover timed against the sum would drift steadily out of sync with
 * the video it is supposed to match.
 *
 * So this prints what the video will actually show, and the table at the end is
 * the thing to time the narration against. Re-run after any edit and re-read it;
 * the offsets move whenever the network does.
 */
async function beat(page: Page, seconds: number, label: string): Promise<void> {
  if (!startedAt) startedAt = Date.now();
  const at = (Date.now() - startedAt) / 1000;
  timeline.push({ at, hold: seconds, label });
  console.log(`  ${mmss(at)}  (${seconds}s hold)  ${label}`);
  await page.waitForTimeout(seconds * 1000);
}

/**
 * Sign in as one of the demo merchants.
 *
 * The wait before filling matters. The form's only submit handler is React's,
 * so a click that lands before hydration falls through to the browser's native
 * submission — a GET carrying the password in the query string, which would then
 * be on camera in the URL bar. The app now disables the button until hydration,
 * but this recording may run against a build that predates that, so the wait
 * stays here too.
 */
async function signIn(page: Page, slug: keyof DemoState["accounts"]): Promise<void> {
  const account = state.accounts[slug as string];
  await go(page, "/login", 1200);

  // Typed rather than filled. `fill()` sets the value in one assignment, which
  // on video looks like the text was pasted by a machine — which it was.
  await typeInto(page, page.getByLabel("Email"), account.email, 42);
  await typeInto(page, page.getByLabel("Password"), account.password, 42);
  await click(page, page.getByRole("button", { name: /sign in/i }));
  await page.waitForURL((url) => url.pathname.startsWith("/app"), { timeout: 90_000 });
  await page.waitForTimeout(900);
  await settleCursor(page);
}

/** Sign out through the header menu, so the video shows the tenant changing. */
async function signOut(page: Page): Promise<void> {
  await click(page, page.getByLabel("Account menu"));
  await page.waitForTimeout(700);
  await click(page, page.getByRole("menuitem", { name: /sign out/i }), 380);
  await page.waitForURL((url) => !url.pathname.startsWith("/app"), { timeout: 60_000 });
  await page.waitForTimeout(600);
  await settleCursor(page);
}

/**
 * Navigate, then settle briefly.
 *
 * `networkidle` waits for the network to go quiet for half a second, and this
 * app never quite does — the alert banner holds a WebSocket open, and Realtime
 * subscribes on the case pages. Waiting for it added two to four seconds to
 * every one of twenty-odd navigations, which is most of the gap between the
 * beats this file schedules and the length of the video it produces.
 */
async function go(page: Page, url: string, settleMs = 700): Promise<void> {
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(settleMs);
  // A full document load drops the injected cursor, so put it back where it was
  // rather than letting it reappear in the corner between segments.
  await settleCursor(page);
}


/** Open a case detail page by its key in `demo_state.json`. */
async function openCase(page: Page, key: string): Promise<DemoCase> {
  const demoCase = state.cases[key];
  if (!demoCase) throw new Error(`No case ${key} in demo_state.json`);
  await go(page, `/app/cases/${demoCase.case_id}`, 1100);
  await expect(page.getByRole("heading", { name: /^Case /i })).toBeVisible();
  return demoCase;
}

/**
 * Expand one step in the agent timeline.
 *
 * The steps render as buttons labelled with the step name and its timestamp, so
 * a name match has to be a prefix rather than an exact string.
 */
async function expandStep(page: Page, step: string): Promise<void> {
  const trigger = page.getByRole("button", { name: new RegExp(`^${step}`, "i") }).first();
  await scrollToLocator(page, trigger, 700);
  await click(page, trigger);
  // Long enough for the panel's own open animation to finish before the beat
  // that talks about what is inside it.
  await page.waitForTimeout(850);
}

/**
 * Scroll to something as an eased animation, and carry on if it is not there.
 *
 * The short timeout inside `scrollToLocator` is the point: Playwright's default
 * action timeout is 30 seconds, so a selector that never matches does not just
 * fail — it silently adds half a minute of dead video between two beats, and the
 * narration timed against them slides out from under the picture.
 */
async function glideTo(page: Page, selector: string): Promise<void> {
  const found = await scrollToLocator(page, page.locator(selector).first(), 950);
  if (!found) console.log(`      (nothing matched ${selector} — skipped the scroll)`);
  await page.waitForTimeout(350);
}

/**
 * Put a live outage on the network page, for real, mid-recording.
 *
 * `/api/simulator/network/downtime` is the obvious way to do this and it returns
 * 404 in production: the simulator router is gated to development environments
 * because it manufactures financial events. So the row goes in directly, with
 * the service role, in the shape that endpoint writes — and the banner picks it
 * up on the next load of the page, because `NetworkAlertBanner` re-reads
 * `/api/network/alerts` rather than trusting a socket payload.
 *
 * Resolved again immediately afterwards, so the app is not left showing an
 * outage that never ends.
 */
async function writeNetworkAlert(live: boolean): Promise<void> {
  const url = process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_KEY;
  if (!url || !key) {
    console.log("  ! SUPABASE_URL / SUPABASE_SERVICE_KEY unset — skipping the live alert");
    return;
  }
  const headers = {
    apikey: key,
    Authorization: `Bearer ${key}`,
    "Content-Type": "application/json",
    Prefer: "return=minimal",
  };
  const now = new Date().toISOString();

  if (live) {
    await fetch(`${url}/rest/v1/network_alerts`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        alert_type: "downtime",
        affected_bank: "SBI",
        affected_method: "upi",
        severity: "high",
        sample_size: 240,
        affected_merchants_count: 3,
        network_wide_success_rate: 0.31,
        baseline_rate: 0.82,
        detected_at: now,
        resolved_at: null,
        metadata: { source: "demo_recording", duration_minutes: 30 },
      }),
    });
    return;
  }

  await fetch(`${url}/rest/v1/network_alerts?resolved_at=is.null`, {
    method: "PATCH",
    headers,
    body: JSON.stringify({ resolved_at: now, updated_at: now }),
  });
}

test("demo recording", async ({ page }) => {
  console.log(`\nRecording against ${test.info().project.use.baseURL}`);
  console.log(`Seeded ${state.generated_at}\n`);

  // ── SEGMENT 1 · the landing page ───────────────────────────────────
  await installCursor(page);
  await go(page, "/", 1200);

  // Where the page content actually sits on the physical screen, so an external
  // capture can be cropped to exactly the viewport with no chrome and no
  // guesswork about the height of the tab strip. `devicePixelRatio` matters:
  // screen capture works in physical pixels, CSS coordinates do not.
  const rect = await page.evaluate(() => ({
    x: window.screenX,
    y: window.screenY + (window.outerHeight - window.innerHeight),
    width: window.innerWidth,
    height: window.innerHeight,
    dpr: window.devicePixelRatio,
  }));
  const rectFile = path.resolve(__dirname, "recordings/viewport.json");
  fs.mkdirSync(path.dirname(rectFile), { recursive: true });
  fs.writeFileSync(rectFile, `${JSON.stringify(rect, null, 2)}\n`);
  console.log(
    `  viewport on screen: ${rect.width}x${rect.height} at ${rect.x},${rect.y} (dpr ${rect.dpr})\n`,
  );
  // Drift in from off-centre so the first thing the viewer sees is a pointer
  // that was already there, rather than one that pops into existence.
  await moveTo(page, 660, 400, 900);
  await beat(page, 4, "S1 · landing hero");
  await scrollBy(page, 520, 1500);
  await beat(page, 4, "S1 · scroll into the pitch");
  await scrollBy(page, 620, 1500);
  await beat(page, 4, "S1 · how it works");

  // ── SEGMENT 2 · sign-up exists, then sign in ───────────────────────
  await go(page, "/signup");
  await expect(page.getByRole("button", { name: /create account/i })).toBeVisible();
  await beat(page, 4, "S2 · sign-up form");

  await signIn(page, "zenith");
  await beat(page, 3, "S2 · signed in as Zenith Learning");

  // ── SEGMENT 3 · the dashboard ──────────────────────────────────────
  await expect(page.getByRole("heading", { name: "Dashboard", exact: true })).toBeVisible();
  await beat(page, 5, "S3 · dashboard KPIs");
  await glideTo(page, "text=Recovery funnel");
  await beat(page, 6, "S3 · recovery funnel");
  await glideTo(page, "text=Recent cases");
  await beat(page, 4, "S3 · recent cases");

  // ── SEGMENT 4 · S1 Suresh — causal diagnosis ───────────────────────
  const suresh = await openCase(page, "S1_suresh");
  await beat(page, 5, `S4 · ${suresh.customer_name} — case header`);
  await expandStep(page, "diagnose");
  await beat(page, 8, "S4 · causal DAG + root cause");
  await glideTo(page, "text=Causal Reasoning");
  await beat(page, 7, "S4 · causal reasoning panel");
  await glideTo(page, "text=What else it could be");
  await beat(page, 5, "S4 · competing hypotheses");

  // ── SEGMENT 5 · the bandit ─────────────────────────────────────────
  await expandStep(page, "decide");
  await beat(page, 8, "S5 · Thompson sampling, arm chosen + alternatives fan");
  await expandStep(page, "uplift check");
  await beat(page, 6, "S5 · uplift bucket");
  await expandStep(page, "guardrail");
  await beat(page, 6, "S5 · RBI / TRAI / consent guardrail");

  // ── SEGMENT 6 · S5 Vikram — reply, handoff, real payment link ──────
  const vikram = await openCase(page, "S5_vikram");
  await beat(page, 5, `S6 · ${vikram.customer_name} — churn intent`);
  await expandStep(page, "listen");
  await beat(page, 8, "S6 · Hinglish reply classified as churn");
  await expandStep(page, "execute");
  await beat(page, 7, "S6 · real Razorpay payment link");
  // HumanHandoffCard renders inside the expanded execute step (CaseTimeline
  // ~line 731), keyed off the handoff execution attempt — not as a panel of its
  // own further down the page.
  await beat(page, 6, "S6 · human handoff card");

  // ── SEGMENT 7 · tenant switch ──────────────────────────────────────
  await signOut(page);
  await beat(page, 3, "S7 · signed out");
  await signIn(page, "kajal");
  await beat(page, 4, "S7 · signed in as Kajal & Co. — different tenant, different data");

  // ── SEGMENT 8 · cases list ─────────────────────────────────────────
  await go(page, "/app/cases");
  await expect(page.getByRole("heading", { name: "Cases", exact: true })).toBeVisible();
  await beat(page, 6, "S8 · cases list, uplift bucket column");

  // ── SEGMENT 9 · S2 Priya — generated message ───────────────────────
  const priya = await openCase(page, "S2_priya");
  await beat(page, 4, `S9 · ${priya.customer_name} — cart abandonment`);
  await expandStep(page, "execute");
  await beat(page, 9, "S9 · Gemini-written Hinglish WhatsApp message");
  await expandStep(page, "decide");
  await beat(page, 6, "S9 · why this arm and not a discount");

  // ── SEGMENT 10 · S3 Aditya — the silent retry ──────────────────────
  const aditya = await openCase(page, "S3_aditya");
  await beat(page, 5, `S10 · ${aditya.customer_name} — recovered silently`);
  await expandStep(page, "uplift check");
  await beat(page, 8, "S10 · transient issuer failure — a retry fixes it, no message needed");

  // ── SEGMENT 11 · S6 Sana — consent ─────────────────────────────────
  const sana = await openCase(page, "S6_sana");
  await beat(page, 4, `S11 · ${sana.customer_name} — opted out`);
  // No step expansion: this case has zero agent_decisions rows. It stopped at
  // the consent gate before a single step ran, which is the whole point of the
  // beat — there is no decision to show because none was made.
  await beat(page, 8, "S11 · do-not-disturb honoured, nothing was ever sent");

  // ── SEGMENT 12 · playbooks ─────────────────────────────────────────
  await go(page, "/app/playbooks");
  await expect(page.getByRole("heading", { name: "Playbooks", exact: true })).toBeVisible();
  await beat(page, 4, "S12 · four playbooks");
  await go(page, "/app/playbooks/checkout_abandonment");
  await beat(page, 6, "S12 · playbook detail — arms and limits");

  // ── SEGMENT 13 · B1 the learning curve ─────────────────────────────
  await go(page, "/app/batch");
  const emptyBatch = await page
    .getByText("No batch run yet")
    .isVisible()
    .catch(() => false);
  if (emptyBatch) {
    // The page reads /api/simulator/batch/latest, which 404s wherever the
    // backend's ENVIRONMENT is "production". Not fatal for the recording, but
    // the narration for this segment has nothing to describe — so say so loudly
    // rather than filming an empty state.
    console.log(
      "  ! /app/batch is empty: the batch endpoint is gated off in production.\n" +
        "    Set the backend Container App's ENVIRONMENT to 'staging' and re-run,\n" +
        "    or record with DEMO_BASE_URL=http://localhost:3000.",
    );
  }
  await beat(page, 6, "S13 · batch — bandit against a fixed rule");
  await glideTo(page, "canvas, svg");
  await beat(page, 9, "S13 · learning curve, bandit overtakes baseline");

  // ── SEGMENT 14 · B2 uplift ROI ─────────────────────────────────────
  await go(page, "/app/roi");
  await expect(page.getByRole("heading", { name: "ROI", exact: true })).toBeVisible();
  await beat(page, 7, "S14 · gross recovered versus incremental");
  await glideTo(page, "text=Where the lift came from");
  await beat(page, 9, "S14 · uplift buckets — persuadable, sure thing, lost cause, DND");

  // ── SEGMENT 15 · B3 the network, live ──────────────────────────────
  await go(page, "/app/network");
  await expect(page.getByRole("heading", { name: "Network", exact: true })).toBeVisible();
  await beat(page, 6, "S15 · federated success rates across merchants");
  await glideTo(page, "text=Success rate by bank and hour");
  await beat(page, 6, "S15 · bank × hour heatmap");

  await writeNetworkAlert(true);
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForTimeout(1200);
  await beat(page, 9, "S15 · SBI UPI outage detected network-wide, retries held back");
  await writeNetworkAlert(false);

  // ── SEGMENT 16 · Sharma — B2B promise to pay ───────────────────────
  await signOut(page);
  await signIn(page, "sharma");
  await beat(page, 4, "S16 · signed in as Sharma Distributors");
  const meera = await openCase(page, "S4_meera");
  await beat(page, 5, `S16 · ${meera.customer_name} — overdue invoice`);
  await expandStep(page, "execute");
  await beat(page, 8, "S16 · graduated B2B sequence, two attempts");
  // PromiseToPayCard renders inside `listen`, not `execute` — it hangs off the
  // classified reply. Expanding the wrong step is how this segment ended up
  // filming a card that was never on screen.
  await expandStep(page, "listen");
  await beat(page, 8, "S16 · promise-to-pay tracked, not chased — 50% now, rest by the 25th");

  // ── SEGMENT 17 · the audit trail ───────────────────────────────────
  await go(page, "/app/audit");
  await expect(page.getByRole("heading", { name: /audit log/i })).toBeVisible();
  await beat(page, 8, "S17 · every decision, every actor, every case");
  await go(page, "/app/settings");
  await beat(page, 3, "S17 · settings");
  // Only Profile and Test mode are live tabs. Playbooks, Compliance and Team are
  // rendered `disabled` on purpose — see settings/page.tsx — so the compliance
  // story is told by the audit log and the batch summary, both of which have
  // real numbers behind them, and not by a settings screen that does not exist
  // yet. Clicking a disabled tab is what failed the first two recordings.
  const testMode = page.getByRole("tab", { name: "Test mode" });
  if (await testMode.isVisible().catch(() => false)) {
    await click(page, testMode);
    await beat(page, 7, "S17 · Razorpay test-mode credentials");
  } else {
    console.log("      (no Test mode tab — this build reports NEXT_PUBLIC_ENVIRONMENT=production)");
    await beat(page, 8, "S17 · settings (no test-mode tab on this build)");
  }

  // ── SEGMENT 18 · close ─────────────────────────────────────────────
  await go(page, "/app");
  await beat(page, 6, "S18 · back to the dashboard — close");

  // The table the voiceover is timed against. Segments are grouped by their
  // "Sn ·" prefix, and each window runs from its first beat to the start of the
  // next segment — which is the span the narration for that segment has to fill,
  // page loads included.
  const total = (Date.now() - startedAt) / 1000;
  const segments: { name: string; from: number; to: number }[] = [];
  for (const row of timeline) {
    const name = row.label.split("·")[0].trim();
    const last = segments[segments.length - 1];
    if (last && last.name === name) last.to = row.at + row.hold;
    else {
      if (last) last.to = row.at;
      segments.push({ name, from: row.at, to: row.at + row.hold });
    }
  }
  if (segments.length) segments[segments.length - 1].to = total;

  console.log(`\n${"─".repeat(64)}\n  SEGMENT WINDOWS — time the voiceover against these\n${"─".repeat(64)}`);
  for (const s of segments) {
    const span = Math.round(s.to - s.from);
    console.log(`  ${s.name.padEnd(5)} ${mmss(s.from)}–${mmss(s.to)}   ${String(span).padStart(3)}s`);
  }
  console.log(`\n  video length: ${mmss(total)}   beats: ${timeline.length}`);
  console.log("  file: tests/e2e/recordings/**/*.webm\n");
});
