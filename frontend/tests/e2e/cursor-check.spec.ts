/**
 * A 20-second check that the cinematics layer actually draws and moves.
 *
 * Kept because "the cursor is missing" and "the cursor is in the wrong place"
 * both look identical to a passing recording run until you watch six minutes of
 * video. This proves the pointer exists, that it lands on what it is about to
 * click, and that scrolling animates rather than jumping.
 *
 *     npx playwright test cursor-check --project=demo
 *
 * Screenshots land beside the video in tests/e2e/recordings/.
 */

import { expect, test } from "@playwright/test";
import path from "node:path";

import { click, installCursor, moveTo, scrollBy, scrollToLocator } from "./lib/cinematics";

const shot = (name: string) => path.resolve(__dirname, `recordings/cursor-${name}.png`);

test("the drawn cursor exists, moves, and lands where it clicks", async ({ page }) => {
  await installCursor(page);
  await page.goto("/login", { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(1200);

  // It should be in the DOM, on top of everything, and not swallowing clicks.
  const cursor = page.locator("[data-demo-cursor]");
  await expect(cursor).toHaveCount(1);
  expect(await cursor.evaluate((el) => getComputedStyle(el).pointerEvents)).toBe("none");
  expect(await cursor.evaluate((el) => getComputedStyle(el).position)).toBe("fixed");

  await moveTo(page, 300, 250, 700);
  const moved = await cursor.boundingBox();
  expect(moved).not.toBeNull();
  await page.screenshot({ path: shot("moved") });

  // The pointer must end up on the field it is about to type into — this is the
  // whole illusion, and an off-by-a-scroll-offset here breaks it silently.
  const email = page.getByLabel("Email");
  await click(page, email);
  const field = await email.boundingBox();
  const tip = await cursor.boundingBox();
  expect(field).not.toBeNull();
  expect(tip).not.toBeNull();
  if (field && tip) {
    const withinX = tip.x >= field.x - 4 && tip.x <= field.x + field.width + 4;
    const withinY = tip.y >= field.y - 4 && tip.y <= field.y + field.height + 4;
    expect(withinX && withinY).toBe(true);
  }
  // And the click has to have actually focused it, not just looked like it did.
  expect(await email.evaluate((el) => el === document.activeElement)).toBe(true);
  await page.screenshot({ path: shot("clicked") });

  // Scrolling should animate: sampled mid-flight, the offset is between the
  // start and the end rather than already at the end.
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(1000);
  const before = await page.evaluate(() => window.scrollY);
  const scrolling = scrollBy(page, 600, 1400);
  await page.waitForTimeout(500);
  const midway = await page.evaluate(() => window.scrollY);
  await scrolling;
  const after = await page.evaluate(() => window.scrollY);

  expect(after).toBeGreaterThan(before);
  expect(midway).toBeGreaterThan(before);
  expect(midway).toBeLessThan(after);
  console.log(`  scroll animated: ${before} → ${midway} → ${after}`);

  // And the locator-targeted variant should move the page too.
  const footerish = page.locator("h2, h3").last();
  const found = await scrollToLocator(page, footerish, 800);
  console.log(`  scrollToLocator resolved: ${found}`);
  await page.screenshot({ path: shot("scrolled") });
});
