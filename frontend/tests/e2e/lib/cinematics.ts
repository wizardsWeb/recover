/**
 * Making an automated browser look like somebody using it.
 *
 * Three things give a Playwright recording away, and none of them are fixed by
 * recording it better:
 *
 * **There is no cursor.** Playwright drives the page through CDP, which
 * dispatches input events directly at coordinates. The operating system pointer
 * never moves, and the built-in recorder draws nothing in its place — so buttons
 * appear to press themselves. The fix is a cursor drawn *inside the page*, moved
 * along a path, with the real click dispatched where it visibly lands.
 *
 * **Movement is instantaneous.** A click is one event at one coordinate. A hand
 * takes a few hundred milliseconds and does not travel in a straight line.
 * Everything here eases, and bows slightly off-axis.
 *
 * **`mouse.wheel` scrolls in lumps.** It dispatches discrete deltas, which reads
 * as stuttering however smooth the capture is. Scrolling here runs as an eased
 * animation inside the page instead.
 *
 * The script below is a plain constant with nothing interpolated into it, and it
 * is delivered either by `addInitScript` (for pages loaded later) or
 * `addScriptTag` (for the page already open). Neither evaluates a built string,
 * which is worth keeping true if this file grows.
 */

import type { Locator, Page } from "@playwright/test";

/** Where the cursor was left, so a navigation does not reset it to the origin. */
let lastX = 720;
let lastY = 450;

/**
 * The pointer, as a data URI rather than markup.
 *
 * `#` has to be percent-encoded inside a data URI or the rest of the SVG is read
 * as a fragment identifier and the image silently fails to load.
 */
const POINTER_SVG =
  "data:image/svg+xml;utf8," +
  "<svg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24'>" +
  "<path d='M5.5 2.5 L5.5 19.2 L9.9 15.1 L12.9 21.6 L15.9 20.2 L12.9 13.8 L19.1 13.4 Z' " +
  "fill='%23ffffff' stroke='%23111111' stroke-width='1.2' stroke-linejoin='round'/></svg>";

const CURSOR_SCRIPT = `
(() => {
  if (window.__demo) return;

  const easeInOutCubic = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
  const easeOutCubic = (t) => 1 - Math.pow(1 - t, 3);
  const POINTER = "${POINTER_SVG}";

  // sessionStorage, not a module variable: an init script runs fresh on every
  // document, so the only way the pointer keeps its position across a navigation
  // is to store it somewhere the new document can read. Same tab, same origin,
  // cleared when the tab closes — exactly the lifetime wanted.
  const KEY = '__demoCursorPos';
  let seeded = { x: Math.round(window.innerWidth / 2), y: Math.round(window.innerHeight / 2) };
  try {
    const saved = JSON.parse(sessionStorage.getItem(KEY) || 'null');
    if (saved && typeof saved.x === 'number') seeded = saved;
  } catch (e) { /* first document, or storage unavailable */ }

  const state = { x: seeded.x, y: seeded.y, el: null, ring: null };

  /**
   * Whichever element actually scrolls on this page.
   *
   * The app shell is h-dvh with overflow-hidden and puts overflow-y-auto on the
   * main column, so the window never scrolls inside /app at all — every
   * window.scrollTo there is a silent no-op, which is why the first cut filmed
   * only the top of every page. The marketing pages outside the shell do scroll
   * the document, so this has to handle both.
   */
  function scroller() {
    const main = document.querySelector('main');
    if (main && main.scrollHeight > main.clientHeight + 4) return main;
    const doc = document.scrollingElement || document.documentElement;
    if (doc && doc.scrollHeight > doc.clientHeight + 4) return doc;
    return main || doc;
  }

  function scrollTopOf(el) {
    return el === document.scrollingElement || el === document.documentElement
      ? window.scrollY
      : el.scrollTop;
  }

  function setScrollTop(el, value) {
    if (el === document.scrollingElement || el === document.documentElement) {
      window.scrollTo(0, value);
    } else {
      el.scrollTop = value;
    }
  }

  function build() {
    if (state.el && document.body.contains(state.el)) return;
    if (!document.body) return;

    const cursor = document.createElement('div');
    cursor.setAttribute('data-demo-cursor', '');
    Object.assign(cursor.style, {
      position: 'fixed', left: '0', top: '0', width: '24px', height: '24px',
      backgroundImage: 'url("' + POINTER + '")',
      backgroundRepeat: 'no-repeat', backgroundSize: '24px 24px',
      zIndex: '2147483647', pointerEvents: 'none', willChange: 'transform',
      // Keeps the pointer legible over both the pale cards and the dark
      // heatmap cells, without outlining it.
      filter: 'drop-shadow(0 1px 2px rgba(0,0,0,.45))',
      transform: 'translate(' + state.x + 'px,' + state.y + 'px)',
    });

    const ring = document.createElement('div');
    Object.assign(ring.style, {
      position: 'fixed', left: '0', top: '0', width: '10px', height: '10px',
      marginLeft: '-5px', marginTop: '-5px', borderRadius: '50%',
      border: '2px solid rgba(20,20,20,.55)', zIndex: '2147483646',
      pointerEvents: 'none', opacity: '0', willChange: 'transform,opacity',
    });

    document.body.appendChild(cursor);
    document.body.appendChild(ring);
    state.el = cursor;
    state.ring = ring;
  }

  function place(x, y) {
    state.x = x; state.y = y;
    if (state.el) state.el.style.transform = 'translate(' + x + 'px,' + y + 'px)';
    try { sessionStorage.setItem(KEY, JSON.stringify({ x: x, y: y })); } catch (e) { /* ignore */ }
  }

  window.__demo = {
    ensure(x, y) {
      build();
      if (typeof x === 'number') place(x, y);
      else place(state.x, state.y);
      return { x: state.x, y: state.y };
    },

    /**
     * Glide to a point over ms, bowing off the straight line.
     *
     * The bow is perpendicular to travel and scales with distance, which is
     * roughly what a hand does. Without it, long moves read as a ruler being
     * drawn across the screen. Short hops stay straight — a bowed 40px move
     * looks like a twitch.
     */
    move(tx, ty, ms) {
      build();
      const sx = state.x, sy = state.y;
      const dx = tx - sx, dy = ty - sy;
      const dist = Math.hypot(dx, dy);
      if (dist < 1) return Promise.resolve();
      const bow = dist > 120 ? Math.min(dist * 0.12, 46) : 0;
      const nx = -dy / dist, ny = dx / dist;
      const start = performance.now();
      const dur = Math.max(ms, 120);

      return new Promise((resolve) => {
        function frame(now) {
          const t = Math.min((now - start) / dur, 1);
          const e = easeInOutCubic(t);
          const arc = Math.sin(Math.PI * t) * bow;
          place(sx + dx * e + nx * arc, sy + dy * e + ny * arc);
          if (t < 1) requestAnimationFrame(frame);
          else resolve();
        }
        requestAnimationFrame(frame);
      });
    },

    /** The press: the pointer dips, a ring expands and fades where it landed. */
    press() {
      build();
      const { x, y } = state;
      const ring = state.ring;
      ring.style.transition = 'none';
      ring.style.transform = 'translate(' + x + 'px,' + y + 'px) scale(.4)';
      ring.style.opacity = '.9';
      state.el.style.transform = 'translate(' + x + 'px,' + y + 'px) scale(.86)';

      return new Promise((resolve) => {
        requestAnimationFrame(() => {
          ring.style.transition =
            'transform 420ms cubic-bezier(.22,1,.36,1), opacity 420ms ease-out';
          ring.style.transform = 'translate(' + x + 'px,' + y + 'px) scale(3.2)';
          ring.style.opacity = '0';
          setTimeout(() => {
            state.el.style.transform = 'translate(' + x + 'px,' + y + 'px) scale(1)';
            resolve();
          }, 130);
        });
      });
    },

    /**
     * Scroll the window to targetY as an eased animation.
     *
     * Deliberately not scrollTo({behavior:'smooth'}): the browser's duration is
     * not controllable, so it cannot be matched to a narration beat, and it is
     * skipped altogether under prefers-reduced-motion.
     */
    scrollTo(targetY, ms) {
      const el = scroller();
      if (!el) return Promise.resolve();
      const sy = scrollTopOf(el);
      const max = Math.max(0, el.scrollHeight - el.clientHeight);
      const dy = Math.max(0, Math.min(targetY, max)) - sy;
      if (Math.abs(dy) < 2) return Promise.resolve();
      const start = performance.now();

      return new Promise((resolve) => {
        function frame(now) {
          const t = Math.min((now - start) / Math.max(ms, 160), 1);
          setScrollTop(el, sy + dy * easeOutCubic(t));
          if (t < 1) requestAnimationFrame(frame);
          else resolve();
        }
        requestAnimationFrame(frame);
      });
    },

    /** How far the scrolling element can travel, and where it is now. */
    range() {
      const el = scroller();
      if (!el) return { max: 0, at: 0, viewport: window.innerHeight };
      return {
        max: Math.max(0, el.scrollHeight - el.clientHeight),
        at: scrollTopOf(el),
        viewport: el.clientHeight || window.innerHeight,
      };
    },

    /** Scroll so a given element sits a third of the way down the frame. */
    reveal(el, ms) {
      const sc = scroller();
      if (!sc || !el) return Promise.resolve();
      const rect = el.getBoundingClientRect();
      const base = sc === document.scrollingElement || sc === document.documentElement
        ? rect.top + window.scrollY
        : sc.scrollTop + (rect.top - sc.getBoundingClientRect().top);
      const target = base - (sc.clientHeight || window.innerHeight) / 3;
      return window.__demo.scrollTo(target, ms);
    },
  };

  // Draw immediately if the document is ready, and otherwise as soon as it is.
  // addInitScript deliberately runs at document-start, so on a fresh
  // navigation there is no <body> yet and building has to wait for one.
  if (document.body) {
    window.__demo.ensure();
  } else {
    document.addEventListener('DOMContentLoaded', () => window.__demo.ensure(), { once: true });
  }
})();
`;

interface DemoWindow {
  __demo?: {
    ensure: (x?: number, y?: number) => { x: number; y: number };
    move: (x: number, y: number, ms: number) => Promise<void>;
    press: () => Promise<void>;
    scrollTo: (y: number, ms: number) => Promise<void>;
    range: () => { max: number; at: number; viewport: number };
    reveal: (el: Element, ms: number) => Promise<void>;
  };
}

/** Register the cursor for this page and every page it navigates to. */
export async function installCursor(page: Page): Promise<void> {
  await page.addInitScript(CURSOR_SCRIPT);
  await settleCursor(page);
}

/**
 * Make sure the cursor exists here, at the position it was left.
 *
 * `addInitScript` only reaches documents loaded after it was registered, so the
 * page already open when `installCursor` ran needs the script delivered
 * directly. A client-side route change keeps the same document and the cursor
 * survives it, which is why this checks before injecting rather than injecting
 * every time.
 */
export async function settleCursor(page: Page): Promise<void> {
  const present = await page
    .evaluate(() => Boolean((window as DemoWindow).__demo))
    .catch(() => false);
  if (!present) {
    await page.addScriptTag({ content: CURSOR_SCRIPT }).catch(() => {});
  }
  await page
    .evaluate(
      ([x, y]) => (window as DemoWindow).__demo?.ensure(x, y),
      [lastX, lastY] as const,
    )
    .catch(() => {});
}

/** Glide the cursor to an absolute viewport point. */
export async function moveTo(page: Page, x: number, y: number, ms = 620): Promise<void> {
  await page
    .evaluate(
      ([tx, ty, dur]) => (window as DemoWindow).__demo?.move(tx, ty, dur),
      [x, y, ms] as const,
    )
    .catch(() => {});
  lastX = x;
  lastY = y;
  // Keep Playwright's own pointer in step, so hover styles match what the drawn
  // cursor is sitting on.
  await page.mouse.move(x, y).catch(() => {});
}

/**
 * Glide to a locator's centre, scrolling it into view first.
 *
 * Returns the point it landed on so the caller can see whether it resolved at
 * all — a missing element means the click should be skipped rather than fired
 * somewhere the cursor never went.
 */
export async function moveToLocator(
  page: Page,
  locator: Locator,
  ms = 620,
): Promise<{ x: number; y: number } | null> {
  await locator.scrollIntoViewIfNeeded({ timeout: 5000 }).catch(() => {});
  const box = await locator.boundingBox().catch(() => null);
  if (!box) return null;
  const x = Math.round(box.x + box.width / 2);
  const y = Math.round(box.y + box.height / 2);
  await moveTo(page, x, y, ms);
  return { x, y };
}

/** Move to something, show the press, then actually click it. */
export async function click(page: Page, locator: Locator, ms = 620): Promise<void> {
  await moveToLocator(page, locator, ms);
  await page.evaluate(() => (window as DemoWindow).__demo?.press()).catch(() => {});
  await locator.click({ timeout: 20_000 });
  await page.waitForTimeout(180);
}

/** Move to a field, click it, then type character by character. */
export async function type(page: Page, locator: Locator, text: string, delay = 55): Promise<void> {
  await click(page, locator, 520);
  await locator.pressSequentially(text, { delay });
  await page.waitForTimeout(220);
}

/** Eased scroll by a delta, in pixels, on whichever element actually scrolls. */
export async function scrollBy(page: Page, dy: number, ms = 900): Promise<void> {
  await page
    .evaluate(
      ([delta, dur]) => {
        const demo = (window as DemoWindow).__demo;
        if (!demo) return undefined;
        return demo.scrollTo(demo.range().at + delta, dur);
      },
      [dy, ms] as const,
    )
    .catch(() => {});
}

/** How far the scrolling element can travel, and where it currently is. */
export async function scrollRange(
  page: Page,
): Promise<{ max: number; at: number; viewport: number }> {
  return page
    .evaluate(
      () =>
        (window as DemoWindow).__demo?.range() ?? {
          max: 0,
          at: 0,
          viewport: window.innerHeight,
        },
    )
    .catch(() => ({ max: 0, at: 0, viewport: 900 }));
}

/** Eased scroll to an absolute offset on the scrolling element. */
export async function scrollToOffset(page: Page, y: number, ms = 900): Promise<void> {
  await page
    .evaluate(
      ([target, dur]) => (window as DemoWindow).__demo?.scrollTo(target, dur),
      [y, ms] as const,
    )
    .catch(() => {});
}

/**
 * Eased scroll until a locator sits comfortably in frame.
 *
 * Aims a third of the way down the frame rather than the top edge, which is
 * where the eye expects the thing being talked about to be. The arithmetic runs
 * inside the page, against the element that actually scrolls — which inside the
 * app shell is the main column and not the window.
 */
export async function scrollToLocator(page: Page, locator: Locator, ms = 900): Promise<boolean> {
  try {
    await locator.waitFor({ state: "attached", timeout: 3000 });
    return await locator.evaluate(async (el, duration) => {
      const demo = (window as DemoWindow).__demo;
      if (!demo) return false;
      await demo.reveal(el, duration);
      return true;
    }, ms);
  } catch {
    return false;
  }
}
