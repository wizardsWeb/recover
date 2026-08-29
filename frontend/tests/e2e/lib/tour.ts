/**
 * Moving through the app the way a person would, and showing all of each page.
 *
 * Three problems this exists to solve, all of them visible in the first cut:
 *
 * **Pages were entered by editing the URL.** `page.goto('/app/cases')` is
 * invisible on video — the address bar changes and a new page appears, with
 * nothing connecting them. Navigation here clicks the actual sidebar link, so
 * the viewer sees the cause of every change.
 *
 * **Only the top of each page was ever filmed.** Every page in this app has
 * content below the fold — the funnel under the dashboard KPIs, the compliance
 * summary under the batch chart, the network insights under the heatmap — and a
 * screenshot of the first 900 pixels showed none of it.
 *
 * **Beats started before the page had rendered.** A flat settle after
 * `domcontentloaded` is a guess. The batch page in particular fetches on the
 * server and then has to let Recharts measure its container — it logs
 * `width(-1) and height(-1)` on the first pass — so a beat timed off a fixed
 * delay opened on an empty panel.
 */

import { expect, type Locator, type Page } from "@playwright/test";

import {
  click,
  moveTo,
  scrollRange,
  scrollToLocator,
  scrollToOffset,
  settleCursor,
} from "./cinematics";

/**
 * Wait until the page is actually worth filming.
 *
 * Heading first, then charts: a `<svg>` that has been mounted but not yet
 * measured has a zero-width bounding box, which is exactly the state the batch
 * page's blank frame was captured in.
 */
export async function ready(page: Page, timeout = 25_000): Promise<void> {
  await page
    .locator("main h1, main h2")
    .first()
    .waitFor({ state: "visible", timeout })
    .catch(() => {});

  await page
    .waitForFunction(
      () => {
        const chart = document.querySelector("main svg, main canvas");
        if (!chart) return true;
        return chart.getBoundingClientRect().width > 10;
      },
      undefined,
      { timeout: 10_000 },
    )
    .catch(() => {});

  // Framer Motion staggers most of these pages in. Give the last item time to
  // land so nothing is still fading up when the narration starts.
  await page.waitForTimeout(650);
  await settleCursor(page);
}

interface TourOptions {
  /** Roughly how long the whole descent should take, in seconds. */
  seconds?: number;
  /** Return to the top afterwards. Off by default — the next click is usually in the rail, which is fixed. */
  back?: boolean;
  /** Label for the log, so a run can be read against the voiceover. */
  label?: string;
  /**
   * Stop after this many pixels instead of going to the bottom.
   *
   * The cases table runs to five thousand pixels of rows. Showing that it is
   * long is worth a couple of screens; showing every row is not.
   */
  maxPx?: number;
}

/**
 * Scroll the whole page, top to bottom, in eased steps.
 *
 * Steps rather than one long glide: a single 4-second scroll past four screens
 * of content is unreadable, and pausing between them is what gives the narration
 * something to sit against. The number of steps comes from how much page there
 * actually is, so a short page does not get padded and a long one is not rushed.
 */
export async function tourPage(page: Page, options: TourOptions = {}): Promise<void> {
  const { seconds = 9, back = false, label = "", maxPx } = options;
  const { max: fullRange, viewport } = await scrollRange(page);
  const range = maxPx ? Math.min(fullRange, maxPx) : fullRange;

  if (range < 60) {
    if (label) console.log(`      ${label}: nothing below the fold`);
    await page.waitForTimeout(seconds * 1000);
    return;
  }
  // One step per ~70% of a screen, so consecutive views overlap and the eye can
  // follow what moved rather than being teleported a full screen at a time.
  const steps = Math.max(2, Math.min(6, Math.ceil(range / (viewport * 0.7))));
  const glide = Math.min(1500, Math.max(700, (seconds * 1000) / steps / 2));
  const hold = Math.max(300, (seconds * 1000 - glide * steps) / steps);

  if (label) {
    const capped = maxPx && fullRange > maxPx ? ` (of ${fullRange}px)` : "";
    console.log(`      ${label}: ${range}px${capped} below the fold, ${steps} steps`);
  }

  for (let i = 1; i <= steps; i += 1) {
    await scrollToOffset(page, Math.round((range * i) / steps), glide);
    await page.waitForTimeout(hold);
  }

  if (back) {
    await scrollToOffset(page, 0, 1100);
    await page.waitForTimeout(400);
  }
}

/**
 * Click a link in the left rail and wait for the page it leads to.
 *
 * The rail is `position: fixed`, so it is reachable from anywhere on the page —
 * no need to scroll back to the top before navigating, which is why `tourPage`
 * leaves the scroll position where it ended.
 */
export async function navByRail(page: Page, name: string, expectPath?: string): Promise<void> {
  // Most rail links sit inside <nav>. The DEVELOPMENT group at the bottom —
  // Simulator, Razorpay — does not, so fall back to a page-wide match rather
  // than failing on the one page the coverage list specifically asked for.
  const inNav = page.locator("nav").getByRole("link", { name, exact: true }).first();
  const link = (await inNav.count()) > 0
    ? inNav
    : page.getByRole("link", { name, exact: true }).first();
  await click(page, link, 700);
  if (expectPath) {
    await page.waitForURL((url) => url.pathname === expectPath || url.pathname.startsWith(expectPath), {
      timeout: 45_000,
    });
  }
  await ready(page);
}

/**
 * Open a case by clicking the customer's name in the cases table.
 *
 * Scrolls the row into view first and returns false rather than throwing if the
 * name is not on the page — a persona missing from a tenant's table is a data
 * problem worth reporting, not a reason to abandon the recording.
 */
export async function openCaseByName(page: Page, customerName: string): Promise<boolean> {
  const row = page.getByRole("link", { name: customerName, exact: true }).first();
  const visible = await row.isVisible().catch(() => false);
  if (!visible) {
    const found = await scrollToLocator(page, row, 900);
    if (!found) {
      console.log(`      ! no row for ${customerName} — skipped`);
      return false;
    }
  }
  await click(page, row, 700);
  await page.waitForURL(/\/app\/cases\/[0-9a-f-]{10,}/, { timeout: 45_000 }).catch(() => {});
  await ready(page);
  await expect(page.getByRole("heading", { name: /^Case /i })).toBeVisible({ timeout: 20_000 });
  return true;
}

/**
 * Expand one step in the agent timeline and scroll its contents into view.
 *
 * The trigger's accessible name is the step name followed by its timestamp, so
 * the match has to be a prefix.
 */
export async function expandStep(page: Page, step: string, holdMs = 900): Promise<boolean> {
  const trigger = page.getByRole("button", { name: new RegExp(`^${step}`, "i") }).first();
  const found = await scrollToLocator(page, trigger, 750);
  if (!found) {
    console.log(`      ! no ${step} step on this case — skipped`);
    return false;
  }
  await click(page, trigger);
  await page.waitForTimeout(holdMs);
  // What just opened is usually taller than the space left below the trigger.
  await scrollToLocator(page, trigger, 500);
  return true;
}

/** Move the pointer somewhere harmless, so it is not parked on a tooltip. */
export async function rest(page: Page): Promise<void> {
  const size = page.viewportSize() ?? { width: 1440, height: 900 };
  await moveTo(page, Math.round(size.width * 0.62), Math.round(size.height * 0.52), 700);
}

/** Hover something to bring out its hover state, without clicking it. */
export async function hover(page: Page, locator: Locator, ms = 650): Promise<void> {
  const found = await scrollToLocator(page, locator, 700);
  if (!found) return;
  const box = await locator.boundingBox().catch(() => null);
  if (!box) return;
  await moveTo(page, Math.round(box.x + box.width / 2), Math.round(box.y + box.height / 2), ms);
  await locator.hover({ timeout: 5000 }).catch(() => {});
}
