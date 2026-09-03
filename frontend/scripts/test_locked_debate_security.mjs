import { chromium } from "playwright";
import { spawn } from "child_process";

const PORT = 3055;
const BASE_URL = `http://localhost:${PORT}`;

async function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function waitForServer(url, timeoutMs = 30000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const res = await fetch(url);
      if (res.status === 200 || res.status === 304 || res.status === 404) return true;
    } catch (e) {}
    await sleep(500);
  }
  throw new Error(`Server at ${url} did not become ready within ${timeoutMs}ms`);
}

async function run() {
  console.log("=================================================");
  console.log("TESTING LOCKED DEBATE ROUTE & URL SECURITY GATES");
  console.log("=================================================");

  // Start next server in production mode
  console.log(`Starting Next.js production server on port ${PORT}...`);
  const server = spawn("npx", ["next", "start", "-p", String(PORT)], {
    cwd: process.cwd(),
    env: { ...process.env, PORT: String(PORT), NODE_ENV: "production" },
    stdio: "inherit",
  });

  try {
    await waitForServer(`${BASE_URL}/`);
    console.log("Server is ready. Launching headless browser...");

    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();
    await page.addInitScript(() => {
      window.__TEST_USER__ = { id: "test-user-e2e", email: "test@rebutio.app" };
      localStorage.setItem("rebutio_test_user", "1");
    });

    // 1. Visit /debate/1 (Level 1: Take a Side) -> MUST BE UNLOCKED
    console.log("\n[Test 1] Navigating to /debate/1 (Level 1: Take a Side)...");
    await page.goto(`${BASE_URL}/debate/1`, { waitUntil: "networkidle" });
    await sleep(600);

    const level1Text = await page.textContent("body");
    const isLevel1Briefing = level1Text.includes("Briefing") && level1Text.includes("Take a Side") && level1Text.includes("Start Debate");
    console.log("  Level 1 is accessible with briefing & start button:", isLevel1Briefing);
    if (!isLevel1Briefing) {
      throw new Error("Level 1 should be unlocked and show briefing!");
    }

    // 2. Visit /debate/2 (Level 2: Give a Reason) -> MUST BE LOCKED
    console.log("\n[Test 2] Tampering URL to /debate/2 (Level 2: Give a Reason)...");
    await page.goto(`${BASE_URL}/debate/2`, { waitUntil: "networkidle" });
    await sleep(600);

    const level2Text = await page.textContent("body");
    const isLevel2Locked = level2Text.includes("Level 2 · Locked") || (level2Text.includes("Give a Reason") && level2Text.includes("locked"));
    const hasStartDebateBtn2 = level2Text.includes("Start Debate");
    console.log("  Level 2 lock gate displayed:", isLevel2Locked);
    console.log("  Level 2 Start Debate button hidden:", !hasStartDebateBtn2);
    if (!isLevel2Locked || hasStartDebateBtn2) {
      throw new Error("Level 2 should be strictly locked! Start Debate button must not be visible.");
    }

    // 3. Visit /debate/3 (Level 3: Back It Up) -> MUST BE LOCKED
    console.log("\n[Test 3] Tampering URL to /debate/3 (Level 3: Back It Up)...");
    await page.goto(`${BASE_URL}/debate/3`, { waitUntil: "networkidle" });
    await sleep(600);

    const level3Text = await page.textContent("body");
    const isLevel3Locked = level3Text.includes("Level 3 · Locked") || (level3Text.includes("Back It Up") && level3Text.includes("locked"));
    console.log("  Level 3 lock gate displayed:", isLevel3Locked);
    if (!isLevel3Locked) {
      throw new Error("Level 3 should be strictly locked!");
    }

    // 4. Query param tampering: /debate?topic=uniforms (Topic for Level 2) -> MUST BE LOCKED
    console.log("\n[Test 4] Tampering query param to /debate?topic=uniforms...");
    await page.goto(`${BASE_URL}/debate?topic=uniforms`, { waitUntil: "networkidle" });
    await sleep(600);

    const queryUniformsText = await page.textContent("body");
    const isUniformsLocked = queryUniformsText.includes("Level 2 · Locked") || queryUniformsText.includes("locked");
    const hasStartDebateUniforms = queryUniformsText.includes("Start Debate");
    console.log("  Locked gate shown for locked topic:", isUniformsLocked);
    console.log("  Start debate button hidden:", !hasStartDebateUniforms);
    if (!isUniformsLocked || hasStartDebateUniforms) {
      throw new Error("/debate?topic=uniforms must be locked!");
    }

    // 5. Query param tampering: /debate?level=2 -> MUST BE LOCKED
    console.log("\n[Test 5] Tampering query param to /debate?level=2...");
    await page.goto(`${BASE_URL}/debate?level=2`, { waitUntil: "networkidle" });
    await sleep(600);

    const queryLevel2Text = await page.textContent("body");
    const isQueryLevel2Locked = queryLevel2Text.includes("Level 2 · Locked") || queryLevel2Text.includes("locked");
    console.log("  Locked gate shown for /debate?level=2:", isQueryLevel2Locked);
    if (!isQueryLevel2Locked) {
      throw new Error("/debate?level=2 must be locked!");
    }

    // 6. Non-tampered /debate -> loads current active level (Level 1)
    console.log("\n[Test 6] Normal /debate route (default current node)...");
    await page.goto(`${BASE_URL}/debate`, { waitUntil: "networkidle" });
    await sleep(600);

    const defaultDebateText = await page.textContent("body");
    const isDefaultUnlocked = defaultDebateText.includes("Briefing") && defaultDebateText.includes("Start Debate");
    console.log("  Default /debate loads current unlocked level:", isDefaultUnlocked);
    if (!isDefaultUnlocked) {
      throw new Error("Default /debate should load current unlocked debate!");
    }

    await browser.close();
    console.log("\n=================================================");
    console.log("ALL URL TAMPERING & PROGRESSION LOCK TESTS PASSED!");
    console.log("=================================================");
  } finally {
    server.kill("SIGTERM");
  }
}

run().catch((err) => {
  console.error("Test failed:", err);
  process.exit(1);
});
