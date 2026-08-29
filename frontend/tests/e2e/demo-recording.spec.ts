/**
 * The demo recording.
 *
 * One test, start to finish, producing a single video. Segment numbers here
 * match `docs/voiceover-script.md` exactly.
 *
 * **Everything is clicked, nothing is typed into the address bar.** An earlier
 * cut navigated with `page.goto`, which on video is a page changing for no
 * visible reason. Pages are reached through the left rail and cases through the
 * customer's name in the table, so every transition has a cause on screen.
 *
 * **Every page is scrolled to the bottom.** All of them have content below the
 * fold — the funnel under the dashboard tiles, the compliance summary under the
 * batch chart, the network insights under the heatmap — and the first cut filmed
 * only the top 900 pixels of each.
 *
 * **Beats wait for content, not for a timer.** `ready()` waits for the heading
 * and for any chart to have a measured width. The batch page fetches on the
 * server and then lets Recharts size itself — it logs `width(-1) and height(-1)`
 * on its first pass — so a fixed delay opened the beat on a blank panel, which
 * is exactly the frame that went wrong last time.
 *
 * **No `page.pause()`.** It opens the Playwright Inspector and blocks until a
 * human clicks resume: a frozen video with a devtools window in it.
 *
 * Data comes from `backend/scripts/demo_state.json`. Case ids are only read to
 * know which customer to look for; the opening itself is a click.
 *
 *     cd frontend
 *     npm run demo:record     # Playwright's own 25fps capture
 *     npm run demo:capture    # 60fps screen capture, needs one permission
 */

import { expect, test, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

import { click, installCursor, moveTo, type as typeInto } from "./lib/cinematics";
import { expandStep, hover, navByRail, openCaseByName, ready, rest, tourPage } from "./lib/tour";

interface DemoCase {
  case_id: string;
  merchant: string;
  customer_name: string;
  actual_arm: string;
  actual_status: string;
}

interface DemoState {
  accounts: Record<
    string,
    { email: string; password: string; merchant_id: string; brand_name: string }
  >;
  cases: Record<string, DemoCase>;
  generated_at: string;
}

const state: DemoState = JSON.parse(
  fs.readFileSync(path.resolve(__dirname, "../../../backend/scripts/demo_state.json"), "utf8"),
);

let startedAt = 0;
const timeline: { at: number; hold: number; label: string }[] = [];
const mmss = (s: number) => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`;

/**
 * Hold still so the narration for this beat has room.
 *
 * The offset logged is real elapsed time, not the sum of the holds before it.
 * Navigation, typing and scrolling all cost seconds the holds never account for,
 * so a voiceover timed against the sum drifts steadily out from under the
 * picture. The table printed at the end is the thing to time against.
 */
async function beat(page: Page, seconds: number, label: string): Promise<void> {
  if (!startedAt) startedAt = Date.now();
  const at = (Date.now() - startedAt) / 1000;
  timeline.push({ at, hold: seconds, label });
  console.log(`  ${mmss(at)}  (${seconds}s)  ${label}`);
  await page.waitForTimeout(seconds * 1000);
}

/** Navigate by URL. Only used to enter the app from outside it. */
async function go(page: Page, url: string, settleMs = 900): Promise<void> {
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(settleMs);
  await ready(page);
}

async function signIn(page: Page, slug: string): Promise<void> {
  const account = state.accounts[slug];
  // Typed, not filled: `fill()` assigns the value in one go, which on video is
  // text appearing by magic.
  await typeInto(page, page.getByLabel("Email"), account.email, 40);
  await typeInto(page, page.getByLabel("Password"), account.password, 40);
  await click(page, page.getByRole("button", { name: /sign in/i }));
  await page.waitForURL((url) => url.pathname.startsWith("/app"), { timeout: 90_000 });
  await ready(page);
}

/** Sign out through the header menu, then land back on the login form. */
async function signOut(page: Page): Promise<void> {
  await click(page, page.getByLabel("Account menu"));
  await page.waitForTimeout(650);
  await click(page, page.getByRole("menuitem", { name: /sign out/i }), 360);
  await page.waitForURL((url) => !url.pathname.startsWith("/app"), { timeout: 60_000 });
  await page.waitForTimeout(700);
  await go(page, "/login", 900);
}

/**
 * Put the network back to healthy.
 *
 * The downtime button in segment 15 writes a real alert, and the endpoint's own
 * auto-resolve is thirty minutes out. Left alone, the next run would open on a
 * live outage — and then hit the endpoint's duplicate check when it tried to
 * fire another one.
 */
async function resolveAlerts(): Promise<void> {
  const url = process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_KEY;
  if (!url || !key) {
    console.log("  ! SUPABASE_* unset — any outage will be left standing");
    return;
  }
  const now = new Date().toISOString();
  await fetch(`${url}/rest/v1/network_alerts?resolved_at=is.null`, {
    method: "PATCH",
    headers: {
      apikey: key,
      Authorization: `Bearer ${key}`,
      "Content-Type": "application/json",
      Prefer: "return=minimal",
    },
    body: JSON.stringify({ resolved_at: now, updated_at: now }),
  }).catch(() => {});
}

test("demo recording", async ({ page }) => {
  console.log(`\nRecording against ${test.info().project.use.baseURL}`);
  console.log(`Seeded ${state.generated_at}\n`);

  await resolveAlerts();
  await installCursor(page);

  // ── SEGMENT 1 · the landing page ───────────────────────────────────
  await go(page, "/", 1300);
  await moveTo(page, 680, 400, 900);
  await beat(page, 5, "S1 · landing hero");
  await tourPage(page, { seconds: 13, label: "S1 landing" });
  await beat(page, 3, "S1 · the pitch, end to end");

  // ── SEGMENT 2 · sign-up exists, then sign in ───────────────────────
  await click(page, page.getByRole("link", { name: /sign up/i }).first());
  await page.waitForURL(/\/signup/, { timeout: 45_000 });
  await ready(page);
  await beat(page, 5, "S2 · the sign-up form");

  await click(page, page.getByRole("link", { name: /sign in/i }).first());
  await page.waitForURL(/\/login/, { timeout: 45_000 });
  await ready(page);
  await signIn(page, "zenith");
  await beat(page, 4, "S2 · Zenith Learning, signed in");

  // ── SEGMENT 3 · the dashboard, all of it ───────────────────────────
  await expect(page.getByRole("heading", { name: "Dashboard", exact: true })).toBeVisible();
  await beat(page, 5, "S3 · dashboard KPIs");
  await tourPage(page, { seconds: 15, label: "S3 dashboard" });
  await beat(page, 4, "S3 · the funnel, and recent cases");

  // ── SEGMENT 4 · the cases list, then Suresh ────────────────────────
  await navByRail(page, "Cases", "/app/cases");
  await beat(page, 5, "S4 · every case, with its uplift bucket");
  await tourPage(page, { seconds: 8, label: "S4 cases", maxPx: 1700 });

  await openCaseByName(page, state.cases.S1_suresh.customer_name);
  await beat(page, 5, "S4 · Suresh Iyer — a subscription renewal that failed");
  await tourPage(page, { seconds: 8, label: "S4 case detail" });
  await expandStep(page, "diagnose");
  await beat(page, 9, "S4 · the causal diagnosis, and the root cause");
  await expandStep(page, "uplift check");
  await beat(page, 6, "S4 · would contacting him even help");

  // ── SEGMENT 5 · the bandit and the guardrail ───────────────────────
  await expandStep(page, "decide");
  await beat(page, 9, "S5 · Thompson sampling, and the arms it passed over");
  await expandStep(page, "guardrail");
  await beat(page, 7, "S5 · RBI, TRAI, consent");
  await expandStep(page, "execute");
  await beat(page, 6, "S5 · the retry, and what came back");

  // ── SEGMENT 6 · Vikram — churn, handoff, a real link ───────────────
  await navByRail(page, "Cases", "/app/cases");
  await openCaseByName(page, state.cases.S5_vikram.customer_name);
  await beat(page, 4, "S6 · Vikram Sethi");
  await expandStep(page, "listen");
  await beat(page, 9, "S6 · a Hinglish reply, read as churn");
  await expandStep(page, "execute");
  await beat(page, 9, "S6 · a real Razorpay link, then a human handoff");
  await tourPage(page, { seconds: 7, label: "S6 case detail" });

  // ── SEGMENT 7 · playbooks ──────────────────────────────────────────
  await navByRail(page, "Playbooks", "/app/playbooks");
  await beat(page, 5, "S7 · four playbooks");
  await tourPage(page, { seconds: 7, label: "S7 playbooks" });
  await click(page, page.getByRole("link", { name: /configure/i }).nth(1));
  await page.waitForURL(/\/app\/playbooks\/.+/, { timeout: 45_000 });
  await ready(page);
  await beat(page, 6, "S7 · inside one playbook — arms and limits");
  await tourPage(page, { seconds: 9, label: "S7 playbook detail" });

  // ── SEGMENT 8 · tenant switch ──────────────────────────────────────
  await signOut(page);
  await beat(page, 3, "S8 · signed out");
  await signIn(page, "kajal");
  await beat(page, 5, "S8 · Kajal & Co. — a different tenant entirely");

  // ── SEGMENT 9 · Priya — the generated message ──────────────────────
  await navByRail(page, "Cases", "/app/cases");
  await beat(page, 4, "S9 · Kajal's cases");
  await tourPage(page, { seconds: 6, label: "S9 cases", maxPx: 1300 });
  await openCaseByName(page, state.cases.S2_priya.customer_name);
  await beat(page, 4, "S9 · Priya Menon — a cart abandoned at checkout");
  await expandStep(page, "execute");
  await beat(page, 10, "S9 · the Hinglish message Gemini wrote");
  await expandStep(page, "decide");
  await beat(page, 6, "S9 · why the eight per cent arm, and not a bigger one");

  // ── SEGMENT 10 · Aditya — the silent recovery ──────────────────────
  await navByRail(page, "Cases", "/app/cases");
  await openCaseByName(page, state.cases.S3_aditya.customer_name);
  await beat(page, 4, "S10 · Aditya Rao — recovered, silently");
  await expandStep(page, "diagnose");
  await beat(page, 7, "S10 · a transient issuer failure");
  await expandStep(page, "execute");
  await beat(page, 6, "S10 · a retry, and no message at all");

  // ── SEGMENT 11 · Sana — consent ────────────────────────────────────
  await navByRail(page, "Cases", "/app/cases");
  await openCaseByName(page, state.cases.S6_sana.customer_name);
  await beat(page, 5, "S11 · Sana Khatri — do not disturb");
  await tourPage(page, { seconds: 9, label: "S11 case detail" });
  await beat(page, 4, "S11 · no steps at all, because nothing was allowed to start");

  // ── SEGMENT 12 · the learning curve ────────────────────────────────
  await navByRail(page, "Batch", "/app/batch");
  const emptyBatch = await page
    .getByText("No batch run yet")
    .isVisible()
    .catch(() => false);
  if (emptyBatch) {
    console.log(
      "  ! /app/batch is empty. That endpoint is gated off wherever the backend's\n" +
        "    ENVIRONMENT is 'production' — record against a local stack.",
    );
  }
  await beat(page, 7, "S12 · a bandit against a fixed rule, over 200 cases");
  await hover(page, page.locator("main svg").first());
  await beat(page, 8, "S12 · the crossover at case fifty");
  await tourPage(page, { seconds: 10, label: "S12 batch" });
  await beat(page, 5, "S12 · compliance across the whole run");

  // ── SEGMENT 13 · uplift ROI ────────────────────────────────────────
  await navByRail(page, "ROI", "/app/roi");
  await beat(page, 7, "S13 · gross against incremental");
  await tourPage(page, { seconds: 12, label: "S13 roi" });
  await beat(page, 6, "S13 · the four uplift buckets");

  // ── SEGMENT 14 · the audit trail ───────────────────────────────────
  await navByRail(page, "Audit", "/app/audit");
  await beat(page, 6, "S14 · every decision, every actor, every case");
  await tourPage(page, { seconds: 9, label: "S14 audit" });
  await beat(page, 4, "S14 · a log of reasoning, not of messages");

  // ── SEGMENT 15 · the network, and a live outage ─────────────────────
  await navByRail(page, "Network", "/app/network");
  await beat(page, 6, "S15 · success rates, pooled across merchants");
  await tourPage(page, { seconds: 12, label: "S15 network" });
  await beat(page, 5, "S15 · the bank-by-hour heatmap");

  // The real control, clicked on camera. `/api/simulator/*` is gated to
  // development environments, which is where this is recorded — and why the
  // button is on screen at all.
  const downtime = page.getByRole("button", { name: /SBI UPI downtime/i });
  if (await downtime.isVisible().catch(() => false)) {
    await click(page, downtime);
    await page.waitForTimeout(2600);
    // The banner is at the top of the page; the button is at the bottom.
    await page.evaluate(
      () =>
        (window as unknown as { __demo?: { scrollTo: (y: number, ms: number) => Promise<void> } })
          .__demo?.scrollTo(0, 1100),
    );
    await beat(page, 11, "S15 · SBI UPI drops, and every agent stops retrying into it");
  } else {
    console.log("      ! no downtime control on this build (isLocal is false)");
    await beat(page, 11, "S15 · outage — control unavailable on this build");
  }

  // ── SEGMENT 16 · the simulator ─────────────────────────────────────
  await navByRail(page, "Simulator", "/app/dev/simulator");
  await beat(page, 6, "S16 · the simulator — where all of this came from");
  await tourPage(page, { seconds: 14, label: "S16 simulator" });
  await beat(page, 6, "S16 · fixtures, scenarios, replies, and the event stream");

  // ── SEGMENT 17 · settings and test mode ────────────────────────────
  await navByRail(page, "Settings", "/app/settings");
  await beat(page, 4, "S17 · settings");
  const testMode = page.getByRole("tab", { name: "Test mode" });
  if (await testMode.isVisible().catch(() => false)) {
    await click(page, testMode);
    await beat(page, 7, "S17 · real Razorpay test credentials");
    await tourPage(page, { seconds: 6, label: "S17 settings" });
  } else {
    console.log("      ! no Test mode tab — NEXT_PUBLIC_ENVIRONMENT reports production");
    await beat(page, 7, "S17 · settings — no test-mode tab on this build");
  }

  // ── SEGMENT 18 · Sharma — B2B promise to pay ───────────────────────
  await signOut(page);
  await signIn(page, "sharma");
  await beat(page, 4, "S18 · Sharma Distributors — business to business");
  await navByRail(page, "Cases", "/app/cases");
  await openCaseByName(page, state.cases.S4_meera.customer_name);
  await beat(page, 5, "S18 · Meera Patil — a large invoice, overdue");
  await expandStep(page, "execute");
  await beat(page, 8, "S18 · a graduated sequence, two attempts");
  await expandStep(page, "listen");
  await beat(page, 10, "S18 · a promise to pay, tracked rather than chased");
  await tourPage(page, { seconds: 7, label: "S18 case detail" });

  // ── SEGMENT 19 · close ─────────────────────────────────────────────
  await navByRail(page, "Dashboard", "/app");
  await rest(page);
  await beat(page, 8, "S19 · back to the dashboard — close");

  await resolveAlerts();

  // The table the voiceover is timed against.
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

  console.log(
    `\n${"─".repeat(64)}\n  SEGMENT WINDOWS — time the voiceover against these\n${"─".repeat(64)}`,
  );
  for (const s of segments) {
    const span = String(Math.round(s.to - s.from)).padStart(3);
    console.log(`  ${s.name.padEnd(5)} ${mmss(s.from)}–${mmss(s.to)}   ${span}s`);
  }
  console.log(`\n  video length: ${mmss(total)}   beats: ${timeline.length}`);
  console.log("  file: tests/e2e/recordings/**/*.webm\n");
});
