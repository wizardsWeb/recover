/**
 * Pre-flight for the recording.
 *
 * Every selector the demo depends on, checked in about a minute, so a broken one
 * is found here instead of nine minutes into a take. Three runs of the full
 * recording have already died on a selector that turned out to be a different
 * role, a disabled control, or simply absent — each time after several minutes
 * of video had been shot.
 *
 *     npx playwright test selector-check --project=demo
 */

import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const state = JSON.parse(
  fs.readFileSync(path.resolve(__dirname, "../../../backend/scripts/demo_state.json"), "utf8"),
) as {
  accounts: Record<string, { email: string; password: string }>;
  cases: Record<string, { customer_name: string; merchant: string }>;
};

const RAIL = ["Dashboard", "Cases", "Playbooks", "Network", "ROI", "Audit", "Batch", "Settings"];

test("every selector the recording needs resolves", async ({ page }) => {
  const problems: string[] = [];
  const note = (message: string) => {
    problems.push(message);
    console.log(`  ✗ ${message}`);
  };
  const ok = (message: string) => console.log(`  ✓ ${message}`);

  // ── the marketing pages ──────────────────────────────────────────
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(1200);
  if (await page.getByRole("link", { name: /sign up/i }).first().isVisible().catch(() => false)) {
    ok('landing has a "Sign up" link');
  } else {
    note('landing has NO "Sign up" link');
  }

  await page.goto("/signup", { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(1000);
  if (await page.getByRole("link", { name: /sign in/i }).first().isVisible().catch(() => false)) {
    ok('sign-up page has a "Sign in" link');
  } else {
    note('sign-up page has NO "Sign in" link');
  }

  // ── sign in as Kajal, who owns the most surfaces ─────────────────
  await page.goto("/login", { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(1500);
  await page.getByLabel("Email").fill(state.accounts.kajal.email);
  await page.getByLabel("Password").fill(state.accounts.kajal.password);
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL((u) => u.pathname.startsWith("/app"), { timeout: 60_000 });
  await page.waitForTimeout(1500);
  ok("signed in");

  // ── the rail ─────────────────────────────────────────────────────
  for (const name of RAIL) {
    const link = page.locator("nav").getByRole("link", { name, exact: true }).first();
    if ((await link.count()) === 0) note(`rail link "${name}" is not inside <nav>`);
    else if (!(await link.isVisible().catch(() => false))) note(`rail link "${name}" is hidden`);
    else ok(`rail link "${name}"`);
  }

  // Simulator sits in the DEVELOPMENT group, which is outside <nav>.
  const sim = page.getByRole("link", { name: "Simulator", exact: true }).first();
  if (await sim.isVisible().catch(() => false)) ok('"Simulator" link (outside <nav>)');
  else note('"Simulator" link missing — showDevTools is false on this build');

  if (await page.getByLabel("Account menu").isVisible().catch(() => false)) {
    ok('"Account menu" trigger');
  } else {
    note('"Account menu" trigger missing');
  }

  // ── cases: the persona rows have to be clickable links ───────────
  await page.goto("/app/cases", { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(2000);
  for (const key of ["S2_priya", "S3_aditya", "S6_sana"]) {
    const name = state.cases[key].customer_name;
    if ((await page.getByRole("link", { name, exact: true }).count()) > 0) {
      ok(`cases row link "${name}"`);
    } else {
      note(`no cases row link for "${name}"`);
    }
  }

  // ── playbooks: the Configure links ───────────────────────────────
  await page.goto("/app/playbooks", { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(1500);
  const configureCount = await page.getByRole("link", { name: /configure/i }).count();
  if (configureCount >= 2) ok(`${configureCount} "Configure" links`);
  else note(`only ${configureCount} "Configure" links — the recording clicks .nth(1)`);

  // ── playbook detail: it renders KPI tiles from a Server Component ──
  // Passing a component (rather than an element) across that boundary throws
  // "Only plain objects can be passed to Client Components", which surfaces as
  // an error page rather than a bad status code — so check for the content.
  await page.goto("/app/playbooks/checkout_abandonment", { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(2500);
  const tiles = await page.getByText("Total cases", { exact: true }).count();
  const crashed = await page
    .getByText(/Only plain objects can be passed|Application error|something went wrong/i)
    .count();
  if (crashed > 0) note("playbook detail page is showing an error");
  else if (tiles > 0) ok("playbook detail renders its KPI tiles");
  else note("playbook detail has no KPI tiles — it may have failed to render");

  // ── batch: the chart must have real width, not -1 ─────────────────
  await page.goto("/app/batch", { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(3500);
  if (await page.getByText("No batch run yet").isVisible().catch(() => false)) {
    note("batch page is empty — the simulator endpoint is gated off on this build");
  } else {
    const width = await page
      .locator("main svg")
      .first()
      .evaluate((el) => el.getBoundingClientRect().width)
      .catch(() => 0);
    if (width > 10) ok(`batch chart measured ${Math.round(width)}px wide`);
    else note(`batch chart is ${width}px wide — Recharts never got a size`);
  }

  // ── network: the downtime control ────────────────────────────────
  await page.goto("/app/network", { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(2000);
  if (await page.getByRole("button", { name: /SBI UPI downtime/i }).isVisible().catch(() => false)) {
    ok('"SBI UPI downtime" button');
  } else {
    note('"SBI UPI downtime" button missing — isLocal is false on this build');
  }

  // ── the simulator page's four panels ─────────────────────────────
  await page.goto("/app/dev/simulator", { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(2500);
  for (const panel of ["Fixtures", "Event stream", "Scenario runner", "Reply injector"]) {
    if (await page.getByText(panel, { exact: true }).first().isVisible().catch(() => false)) {
      ok(`simulator panel "${panel}"`);
    } else {
      note(`simulator panel "${panel}" missing`);
    }
  }

  // ── settings: which tabs are actually usable ─────────────────────
  await page.goto("/app/settings", { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(1500);
  for (const tab of ["Profile", "Test mode"]) {
    const trigger = page.getByRole("tab", { name: tab });
    if (!(await trigger.count())) {
      note(`settings tab "${tab}" missing`);
      continue;
    }
    if (await trigger.isDisabled().catch(() => true)) note(`settings tab "${tab}" is disabled`);
    else ok(`settings tab "${tab}" is clickable`);
  }

  // ── every page must actually have something below the fold ───────
  console.log("\n  scrollable range per page:");
  const pages: [string, string][] = [
    ["dashboard", "/app"],
    ["cases", "/app/cases"],
    ["playbooks", "/app/playbooks"],
    ["network", "/app/network"],
    ["roi", "/app/roi"],
    ["audit", "/app/audit"],
    ["batch", "/app/batch"],
    ["settings", "/app/settings"],
    ["simulator", "/app/dev/simulator"],
  ];
  for (const [label, url] of pages) {
    await page.goto(url, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(1800);
    // The app shell scrolls <main>, not the window, so measuring the document
    // here reports zero for every page — which is exactly how the first cut
    // ended up filming only the top of each one.
    const range = await page.evaluate(() => {
      const main = document.querySelector("main");
      if (main && main.scrollHeight > main.clientHeight + 4) {
        return Math.max(0, main.scrollHeight - main.clientHeight);
      }
      const doc = document.scrollingElement || document.documentElement;
      return Math.max(0, doc.scrollHeight - doc.clientHeight);
    });
    console.log(`    ${label.padEnd(11)} ${String(range).padStart(5)}px`);
  }

  console.log("");
  expect(problems, `unresolved selectors:\n  - ${problems.join("\n  - ")}`).toEqual([]);
});
