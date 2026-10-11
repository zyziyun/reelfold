// Try again on a failed project, with the REAL engine sidecar (no mock engine), isolated temp profile, window hidden.
// 0.2.7: Try again on a project made on autopilot spawned `run --pilot 1`, and the run replayed the old failure in the
// same second without starting a stage (the failed stage was never reset). fixture/failed_project.py makes a script
// project on autopilot whose lint stage fails while a marker file exists (a test-only sitecustomize hook, the only
// fake); the marker goes, the row's Try again must run the failed stage on autopilot and the project gets past it.
import {
  _electron as electron,
  expect,
  test,
  type ElectronApplication,
  type Page,
} from "@playwright/test";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { closeApp } from "./closeApp";

let app: ElectronApplication;
let page: Page;
let fx: { dir: string; hook: string; marker: string; exit: number };
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "vsdesk-tryagain-"));
const REPO = path.resolve(import.meta.dirname, "../../../..");
const engineEnv = {
  VSTUDIO_HOME: path.join(tmp, "vhome"),
  VSTUDIO_BATCH_BENCH: path.join(tmp, "bench.json"),
  VSTUDIO_DEFAULT_PERSONA: "1",
  VSTUDIO_LLM_PROVIDER: "none",
  ...Object.fromEntries(
    [
      "SEGMENT_PLAN",
      "PROOFREAD",
      "GLOSSARY",
      "COPY",
      "SCRIPT",
      "PLANNER",
      "INTAKE",
      "OUTPUT_EDIT",
    ].map((t) => [`VSTUDIO_LLM_${t}_PROVIDER`, "none"]),
  ),
};

type Rec = {
  pid: number | null;
  exit: number | null;
  offset: number;
  args: string[];
};
const rec = () =>
  JSON.parse(
    fs.readFileSync(path.join(fx.dir, "desk-pilot.json"), "utf8"),
  ) as Rec;
const eventsFrom = (offset: number) =>
  fs
    .readFileSync(path.join(fx.dir, "desk-pilot.log"))
    .subarray(offset)
    .toString("utf8")
    .split("\n")
    .flatMap((l) => {
      try {
        const e = JSON.parse(l) as {
          event?: string;
          stage?: string;
          state?: string;
        };
        return e && e.event ? [e] : [];
      } catch {
        return [];
      }
    });

test.beforeAll(async () => {
  test.setTimeout(300000);
  const env: NodeJS.ProcessEnv = {
    ...process.env,
    ...engineEnv,
    PYTHONPATH: path.join(REPO, "lib"),
  };
  for (const k of ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "VSTUDIO_PERSONA"])
    delete env[k];
  const out = execFileSync(
    process.env.DESK_PYTHON || "python3",
    [path.join(import.meta.dirname, "fixture/failed_project.py"), tmp],
    { env, encoding: "utf8" },
  );
  fx = JSON.parse(out.trim().split("\n").pop()!);
  expect(fx.exit).toBe(1);
  app = await electron.launch({
    args: [path.resolve(import.meta.dirname, "../..")],
    env: {
      ...env,
      PYTHONPATH: fx.hook,
      TRYAGAIN_FAIL_WHILE: fx.marker,
      DESK_STUDIO: "1",
      DESK_ENGINE_MOCK: "",
      DESK_USER_DATA: path.join(tmp, "profile"),
      DESK_HISTORY_WATCH: "",
      DESK_HIDE_WINDOW: "1",
      DESK_SHARED_CACHE: path.join(tmp, "cache"),
      DESK_HF_HUB: "",
      DESK_SKIP_FIRST_RUN: "1",
      VITE_DEV_SERVER_URL: "",
    },
  });
  page = await app.firstWindow();
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.waitForURL(/^app:\/\/desk\//);
  await page.evaluate(async () => {
    localStorage.setItem("i18n.strict", "1");
    await window.desk.setSettings({ lang: "en" });
  });
  await page.reload();
  await page.waitForURL(/^app:\/\/desk\//);
  expect((await page.evaluate(() => window.desk.engineInfo())).mode).toBe(
    "real",
  );
});

test.afterAll(async () => {
  await closeApp(app);
});

test("Try again on a failed autopilot project re-runs the failed stage on autopilot and gets past it", async () => {
  test.setTimeout(300000);
  await page.evaluate(() => (location.hash = "#/studio"));
  await expect(page.getByTestId("studio")).toBeVisible({ timeout: 30000 });
  const row = page.locator("[data-testid=studio-row][data-kind=project]", {
    hasText: "Failed script",
  });
  await expect(row).toHaveAttribute("data-tone", "error", { timeout: 60000 });
  const before = rec();
  const offset = fs.statSync(path.join(fx.dir, "desk-pilot.log")).size;
  fs.rmSync(fx.marker); // the cause is fixed (a new build): Try again must really run again
  await row.hover();
  await row.locator("xpath=..").getByTestId("row-more").click();
  await page.getByTestId("context-menu").getByTestId("row-retry").click();
  await expect
    .poll(
      () => {
        const r = rec();
        return r.pid !== before.pid && r.exit != null;
      },
      { timeout: 120000 },
    )
    .toBe(true);
  const after = rec();
  expect(after.args).toContain("--autopilot");
  expect(after.args).not.toContain("--pilot");
  const evs = eventsFrom(offset);
  const started = evs
    .filter((e) => e.event === "stage-start")
    .map((e) => e.stage);
  expect(started).toContain("lint"); // the failed stage ran again
  expect(started).not.toContain("draft"); // the finished one is a cache hit
  expect(
    evs.filter((e) => e.event === "job-done").map((e) => e.state),
  ).not.toContain("failed");
  // the Studio moves on: no failed row left
  await expect(
    page.locator("[data-testid=studio-row][data-tone=error]", {
      hasText: "Failed script",
    }),
  ).toHaveCount(0, { timeout: 30000 });
});
