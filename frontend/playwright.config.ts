import { defineConfig, devices } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

/**
 * Playwright, configured for recording a demo rather than for testing.
 *
 * The differences from a test config are deliberate:
 *
 * **One worker, no retries.** Every run produces a video, so a retry would
 * produce a second one and leave you guessing which take is which.
 *
 * **A long timeout.** The recording is a single test that runs for around five
 * minutes by design. Playwright's 30-second default would kill it in the first
 * segment.
 *
 * **1440×900.** Matches the window someone actually uses this dashboard in. The
 * layouts sit in a max-width container, so 1920×1080 spends its extra pixels on
 * empty gutters either side of the content rather than on making anything
 * bigger.
 *
 * The video size is pinned to the viewport. Left to itself Playwright scales the
 * recording to fit a 800×450 box, which turns dense tables into mush.
 */

// The seeder writes the service key it used into backend/.env; the recording
// needs it for one step (see the network segment), so it is loaded here rather
// than asking whoever runs this to export three variables by hand.
const backendEnv = path.resolve(__dirname, "../backend/.env");
if (fs.existsSync(backendEnv)) {
  for (const line of fs.readFileSync(backendEnv, "utf8").split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#") || !trimmed.includes("=")) continue;
    const [key, ...rest] = trimmed.split("=");
    if (!process.env[key.trim()]) process.env[key.trim()] = rest.join("=").trim();
  }
}

const VIEWPORT = { width: 1440, height: 900 };

export default defineConfig({
  testDir: "./tests/e2e",
  // Five minutes of deliberate pauses, plus headroom for a slow cold start on
  // the Container App.
  timeout: 20 * 60 * 1000,
  expect: { timeout: 30_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  outputDir: "./tests/e2e/recordings",
  use: {
    // Localhost by default, and not for convenience. Recording against the
    // deployment costs about two and a half minutes of pure inter-region
    // latency across the run, and three things simply do not appear there: the
    // batch learning curve and the dev simulator are gated off wherever the
    // backend's ENVIRONMENT is "production", and the test-mode credentials tab
    // is gated on a NEXT_PUBLIC_ value baked in at build time. The data is the
    // same either way — the deployment and a local stack point at one Supabase
    // project. Override to film the deployed URL anyway:
    //
    //     DEMO_BASE_URL=https://…azurecontainerapps.io npx playwright test --project=demo
    baseURL: process.env.DEMO_BASE_URL ?? "http://localhost:3000",
    viewport: VIEWPORT,
    video: { mode: "on", size: VIEWPORT },
    screenshot: "off",
    trace: "off",
    // The deployed app is a region away; every navigation pays for it.
    navigationTimeout: 90_000,
    actionTimeout: 30_000,
  },
  projects: [
    {
      name: "demo",
      use: {
        ...devices["Desktop Chrome"],
        viewport: VIEWPORT,
        // Playwright's own recorder is a fallback, not the good take. It is
        // hard-capped at 25fps — measured, not assumed: a 370-second run came
        // out as exactly 9,256 frames — and it draws no cursor at all. For the
        // final video, capture the headed window externally at 60fps and use
        // this only to check the run completed.
        video: { mode: "on", size: VIEWPORT },
        // Headed, because an external recorder needs a real window to point at.
        headless: false,
        // A demo should show the product's own motion, so no reduced-motion
        // override, even though it would make timings more repeatable.
        launchOptions: {
          args: [
            "--force-color-profile=srgb",
            "--font-render-hinting=none",
            // Pinned so a crop filter can be written against a known rectangle.
            "--window-position=0,0",
            // Hides the "Chrome is being controlled by automated software"
            // infobar, which is otherwise the first thing in frame.
            "--disable-infobars",
            "--hide-crash-restore-bubble",
          ],
        },
      },
    },
  ],
});
