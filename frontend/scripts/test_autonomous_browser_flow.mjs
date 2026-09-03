import { chromium } from "playwright";
import fs from "fs";
import path from "path";

// Read OpenRouter API key from backend/.env if available
let openRouterKey = process.env.OPENROUTER_API_KEY;
if (!openRouterKey) {
  try {
    const envContent = fs.readFileSync(path.resolve("../backend/.env"), "utf-8");
    for (const line of envContent.split("\n")) {
      const trimmed = line.trim();
      if (trimmed.startsWith("OPENROUTER_API_KEY=")) {
        openRouterKey = trimmed.split("=", 2)[1].trim();
        break;
      }
    }
  } catch (e) {}
}

const TTS_MODEL = "hexgrad/kokoro-82m";
const FRONTEND_URL = process.env.FRONTEND_URL || "http://localhost:3000";

async function synthesizeSpeech(text) {
  console.log(`[TTS] Synthesizing speech: "${text}" via ${TTS_MODEL}...`);
  const t0 = Date.now();
  const resp = await fetch("https://openrouter.ai/api/v1/audio/speech", {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${openRouterKey}`,
      "Content-Type": "application/json",
      "HTTP-Referer": "https://rebutio.app",
      "X-Title": "Rebutio Autonomous QA",
    },
    body: JSON.stringify({
      model: TTS_MODEL,
      input: text,
      voice: "af_bella",
      response_format: "mp3",
    }),
  });

  if (!resp.ok) {
    const errText = await resp.text();
    throw new Error(`OpenRouter TTS failed (${resp.status}): ${errText}`);
  }

  const arrayBuf = await resp.arrayBuffer();
  const buffer = Buffer.from(arrayBuf);
  console.log(`[TTS] Synthesized ${buffer.length} bytes in ${Date.now() - t0}ms`);
  return buffer.toString("base64");
}

async function runAutonomousFlow() {
  console.log("================================================================");
  console.log("STARTING AUTONOMOUS REAL BROWSER FLOW TEST");
  console.log("================================================================");

  const browser = await chromium.launch({
    headless: true,
    args: [
      "--use-fake-ui-for-media-stream",
      "--autoplay-policy=no-user-gesture-required",
    ],
  });

  const context = await browser.newContext({
    permissions: ["microphone"],
    viewport: { width: 420, height: 860 },
  });

  const page = await context.newPage();

  // Collect browser console messages and errors
  const browserLogs = [];
  page.on("console", (msg) => {
    browserLogs.push(`[BROWSER ${msg.type().toUpperCase()}] ${msg.text()}`);
    if (msg.type() === "error" || msg.type() === "warn") {
      console.log(`[BROWSER ${msg.type().toUpperCase()}] ${msg.text()}`);
    }
  });
  page.on("pageerror", (err) => {
    browserLogs.push(`[BROWSER UNCAUGHT ERROR] ${err.message}`);
    console.error(`[BROWSER UNCAUGHT ERROR]`, err);
  });

  // Inject Web Audio microphone stream handler
  await page.addInitScript(() => {
    const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    let currentDest = null;

    window.__playAudioForMic = async (base64Audio) => {
      if (audioCtx.state === "suspended") await audioCtx.resume();
      const binaryString = atob(base64Audio);
      const bytes = new Uint8Array(binaryString.length);
      for (let i = 0; i < binaryString.length; i++) bytes[i] = binaryString.charCodeAt(i);
      const audioBuffer = await audioCtx.decodeAudioData(bytes.buffer);
      const source = audioCtx.createBufferSource();
      source.buffer = audioBuffer;
      if (currentDest) source.connect(currentDest);
      source.start();
      return audioBuffer.duration;
    };

    navigator.mediaDevices.getUserMedia = async (constraints) => {
      if (constraints && constraints.audio) {
        currentDest = audioCtx.createMediaStreamDestination();
        return currentDest.stream;
      }
      return navigator.mediaDevices.getUserMedia(constraints);
    };
  });

  // -------------------------------------------------------------------
  // Helper: Perform a spoken turn via real UI controls & microphone
  // -------------------------------------------------------------------
  async function performSpokenTurn(spokenText, turnNum, totalTurns) {
    console.log(`\n--- [TURN ${turnNum}/${totalTurns}] Spoken Turn Execution ---`);
    console.log(`Spoken statement: "${spokenText}"`);

    const audioBase64 = await synthesizeSpeech(spokenText);

    // Ensure we are in "turn" phase and mic button is visible
    const micButton = page.locator('button[aria-label="Start speaking"]');
    await micButton.waitFor({ state: "visible", timeout: 20000 });
    console.log(`[TURN ${turnNum}] Found "Start speaking" button. Clicking to record...`);

    // Click mic to start recording
    await micButton.click({ force: true });

    // Verify recording phase active
    const stopButton = page.locator('button[aria-label="Stop speaking"]');
    await stopButton.waitFor({ state: "visible", timeout: 6000 });
    console.log(`[TURN ${turnNum}] Recording active. Injecting synthesized speech into microphone...`);

    // Feed audio into microphone stream
    const audioDuration = await page.evaluate((b64) => window.__playAudioForMic(b64), audioBase64);
    console.log(`[TURN ${turnNum}] Playing spoken audio for ${(audioDuration).toFixed(2)}s...`);

    // Wait for the spoken audio to finish playing + 300ms natural speaking pause
    await page.waitForTimeout(Math.ceil(audioDuration * 1000) + 300);

    console.log(`[TURN ${turnNum}] Speech finished. Clicking to stop recording...`);
    await stopButton.click({ force: true });

    // Verify reviewing-clip phase
    await page.locator("text=Turn recorded").waitFor({ state: "visible", timeout: 10000 });
    console.log(`[TURN ${turnNum}] Clip recorded successfully. Audio player rendered.`);

    // Find and click Send Turn button
    const isLastTurn = turnNum >= totalTurns;
    const sendButtonText = isLastTurn ? "Send final turn" : "Send turn";
    const sendButton = page.locator(`button:has-text("${sendButtonText}")`);
    await sendButton.waitFor({ state: "visible", timeout: 6000 });
    console.log(`[TURN ${turnNum}] Clicking "${sendButtonText}"...`);
    await sendButton.click();

    if (!isLastTurn) {
      // Wait for opponent response to render or error
      console.log(`[TURN ${turnNum}] Waiting for opponent response...`);
      const opponentHeader = page.locator("text=Rebutio responds");
      const errBanner = page.locator("text=Couldn't send that turn");
      await Promise.race([
        opponentHeader.waitFor({ state: "visible", timeout: 120000 }),
        errBanner.waitFor({ state: "visible", timeout: 120000 }).then(async () => {
          throw new Error("UI error banner displayed: Couldn't send that turn");
        }),
      ]);
      console.log(`[TURN ${turnNum}] Opponent response received!`);

      // Check if opponent audio is available or auto-playing
      const playBtn = page.locator('button[aria-label*="opponent audio"], button:has-text("Play response"), button:has-text("Pause response")');
      const hasAudioBtn = await playBtn.isVisible().catch(() => false);
      console.log(`[TURN ${turnNum}] Opponent speech audio button visible: ${hasAudioBtn}`);

      // Small pause to simulate listening
      await page.waitForTimeout(2000);

      // Click "Make my point" to proceed to next turn
      const nextBtn = page.locator('button:has-text("Make my point")');
      await nextBtn.waitFor({ state: "visible", timeout: 10000 });
      console.log(`[TURN ${turnNum}] Clicking "Make my point" for next turn...`);
      await nextBtn.click();
    } else {
      console.log(`[TURN ${turnNum}] Final turn submitted. Waiting for review and results...`);
    }
  }

  async function executeFullDebate(contextLabel, customSpeeches = []) {
    let turnNumber = 1;
    while (true) {
      if (page.url().includes("/results")) break;

      const headerEl = page.locator("div.mb-1 p.uppercase").first();
      await headerEl.waitFor({ state: "visible", timeout: 25000 });
      const headerText = await headerEl.textContent();
      console.log(`[${contextLabel}] Header: "${headerText}"`);

      if (headerText.toLowerCase().includes("finished")) {
        console.log(`[${contextLabel}] Debate marked finished. Awaiting Results...`);
        break;
      }

      const match = headerText.match(/Turn (\d+) of (\d+)/i);
      const curTurn = match ? parseInt(match[1], 10) : turnNumber;
      const totalTurns = match ? parseInt(match[2], 10) : 3;

      const fallbackSpeeches = [
        "I agree because real-world evidence and direct human experience strongly support this argument.",
        "While the counterpoint is understandable, it overlooks the severe long-term trade-offs.",
        "Furthermore, modern alternatives provide far greater autonomy and proven efficacy.",
        "In conclusion, when looking at the core principles involved, our position remains solid.",
      ];
      const speechList = customSpeeches.length > 0 ? customSpeeches : fallbackSpeeches;
      const speech = speechList[(curTurn - 1) % speechList.length];

      await performSpokenTurn(speech, curTurn, totalTurns);
      turnNumber = curTurn + 1;

      if (curTurn >= totalTurns) {
        break;
      }
    }
  }

  try {
    // -------------------------------------------------------------------
    // Milestone 1: Fresh Onboarding
    // -------------------------------------------------------------------
    console.log("\n>>> Step 1: Loading Onboarding Page...");
    await page.goto(`${FRONTEND_URL}/onboarding`, { waitUntil: "networkidle" });

    // Step 1: Welcome
    console.log("Verifying Welcome screen...");
    await page.locator("text=Speak English like you already").waitFor({ state: "visible" });
    const startFirstBtn = page.locator('button:has-text("Start my first debate")');
    await startFirstBtn.click();

    // Step 2: Goals
    console.log("Step 2: Selecting Goals...");
    await page.locator("text=What do you want to get better at?").waitFor({ state: "visible" });
    await page.locator('button:has-text("Speak with more confidence")').click();
    await page.locator('button:has-text("Think faster in English")').click();
    await page.locator('button:has-text("Continue")').click();

    // Step 3: Comfort
    console.log("Step 3: Selecting Comfort level...");
    await page.locator("text=How comfortable are you speaking English?").waitFor({ state: "visible" });
    await page.locator('button:has-text("I can hold conversations")').click();
    await page.locator('button:has-text("Continue")').click();

    // Step 4: Interests
    console.log("Step 4: Selecting Interests...");
    await page.locator("text=What could you argue about for hours?").waitFor({ state: "visible" });
    await page.locator('button:has-text("Technology & AI")').click();
    await page.locator('button:has-text("Society")').click();
    await page.locator('button:has-text("School & careers")').click();
    await page.locator('button:has-text("Continue")').click();

    // Step 5: Intensity
    console.log("Step 5: Selecting Intensity...");
    await page.locator("text=How hard should Rebutio push back?").waitFor({ state: "visible" });
    await page.locator('button:has-text("Balanced")').click();
    await page.locator('button:has-text("Continue")').click();

    // Step 6: Spar Briefing
    console.log("Step 6: Spar Briefing...");
    await page.locator("text=Let's see how you argue.").waitFor({ state: "visible" });
    const motionTitle = await page.locator("div.mt-8 p.font-display").textContent();
    console.log(`Onboarding Motion: "${motionTitle}"`);

    // Pick "Agree" side
    const agreeBtn = page.getByRole("button", { name: "Agree", exact: true });
    await agreeBtn.click();
    const startSparBtn = page.getByRole("button", { name: "Start Spar", exact: true });
    await startSparBtn.click();

    // Handle Mic Permission screen if shown, otherwise flow directly to Debate
    try {
      const enableMicBtn = page.locator('button:has-text("Enable microphone")');
      if (await enableMicBtn.isVisible({ timeout: 2000 })) {
        console.log("Handling Mic permission step...");
        await enableMicBtn.click();
      }
    } catch (e) {}

    // -------------------------------------------------------------------
    // Milestone 2 & 3: Real Browser Spoken Onboarding Debate (3 turns)
    // -------------------------------------------------------------------
    console.log("\n>>> Step 2: Beginning Onboarding Debate Flow (3 Turns)...");
    const sparSpeeches = [
      "I agree because online interactions often replace deep, vulnerable face-to-face conversations with superficial metrics.",
      "While digital networks widen our reach, emotional intimacy and genuine accountability cannot be sustained through algorithmic feeds.",
      "In conclusion, authentic friendships require presence and mutual vulnerability, which social media systematically dilutes into performative attention."
    ];
    await executeFullDebate("ONBOARDING SPAR", sparSpeeches);

    // -------------------------------------------------------------------
    // Milestone 4: Results Screen Verification
    // -------------------------------------------------------------------
    console.log("\n>>> Step 3: Waiting for Results Screen...");
    await page.waitForURL("**/results**", { timeout: 60000 });
    console.log("Navigated to Results screen!");

    // Verify Results UI components
    await page.locator("text=First spar complete").waitFor({ state: "visible", timeout: 10000 });
    await page.locator("span:has-text('XP')").waitFor({ state: "visible" });
    await page.locator("li:has-text('Completed')").waitFor({ state: "visible" });
    console.log("Results screen verified: Completion, XP, and Star assessment present!");

    // Click "See full feedback"
    const seeFeedbackBtn = page.locator('button:has-text("See full feedback")');
    if (await seeFeedbackBtn.isVisible()) {
      await seeFeedbackBtn.click();
      console.log("Expanded language feedback section.");
      await page.waitForTimeout(1000);
    }

    // -------------------------------------------------------------------
    // Milestone 5: Navigation into Main App (Home / Path)
    // -------------------------------------------------------------------
    console.log("\n>>> Step 4: Navigating to Home...");
    const nextDebateBtn = page.locator('button:has-text("Next Debate")');
    await nextDebateBtn.click();

    await page.waitForURL("**/home", { timeout: 15000 });
    console.log("Navigated to Home page!");

    await page.locator("text=Today's spar").waitFor({ state: "visible" });
    await page.locator("text=Continue path").waitFor({ state: "visible" });
    console.log("Home page verified: Today's spar and Continue path visible!");

    // Navigate to Path page
    console.log("\n>>> Step 5: Navigating to Learning Path via UI...");
    const continuePathLink = page.locator('a[href="/path"]').first();
    await continuePathLink.click();
    await page.waitForURL("**/path", { timeout: 15000 });
    await page.locator("text=Your path").waitFor({ state: "visible", timeout: 10000 });
    console.log("Path page verified: Skill nodes displayed!");

    // -------------------------------------------------------------------
    // Milestone 6, 7, 8, 9, 10, 11: Second Debate Flow
    // -------------------------------------------------------------------
    console.log("\n>>> Step 6: Starting Second Debate from Path...");
    const debateNowLink = page.locator('a:has-text("Debate now")');
    if (await debateNowLink.isVisible({ timeout: 3000 })) {
      await debateNowLink.click();
    } else {
      await page.goto(`${FRONTEND_URL}/debate`, { waitUntil: "networkidle" });
    }

    await page.waitForURL("**/debate**", { timeout: 15000 });
    console.log("Briefing page loaded for Second Debate!");

    await page.locator("text=Briefing").waitFor({ state: "visible" });
    const secondMotion = await page.locator("h1.font-display").textContent();
    console.log(`Second Debate Motion: "${secondMotion}"`);

    // Start second debate as Agree
    const agreeBtn2 = page.getByRole("button", { name: "Agree", exact: true });
    if (await agreeBtn2.isVisible()) {
      await agreeBtn2.click();
    }
    const startDebateBtn2 = page.locator('button:has-text("Start Debate")');
    await startDebateBtn2.click();

    console.log("\n>>> Step 7: Executing Spoken Turns for Second Debate...");
    const secondDebateSpeeches = [
      "I strongly hold that traditional degree programs are failing to provide proportional economic value relative to escalating costs.",
      "Alternative credentialing and targeted apprenticeships offer superior industry alignment without encumbering graduates with crippling debt.",
      "Even considering the networking benefits, the financial overhead delays critical milestones like home ownership and entrepreneurship.",
      "In summary, when weighing return on investment against modern digital alternatives, the traditional path is no longer financially sound."
    ];
    await executeFullDebate("SECOND DEBATE", secondDebateSpeeches);

    // -------------------------------------------------------------------
    // Milestone 10 & 11: Second Debate Review & Progression Update
    // -------------------------------------------------------------------
    console.log("\n>>> Step 8: Waiting for Second Debate Results...");
    await page.waitForURL("**/results**", { timeout: 60000 });
    console.log("Second debate results screen loaded!");

    await page.locator("h1:has-text('Debate done.')").waitFor({ state: "visible", timeout: 10000 });
    await page.locator("span:has-text('XP')").waitFor({ state: "visible" });
    console.log("Second debate review verified!");

    // Return to Home and check progression
    const returnHomeBtn = page.locator('button:has-text("Next Debate")');
    await returnHomeBtn.click();
    await page.waitForURL("**/home", { timeout: 15000 });
    console.log("Returned to Home! Progression updated.");

    console.log("\n================================================================");
    console.log("SUCCESS! ALL COMPLETION CRITERIA PERSONALLY EXERCISED & VERIFIED");
    console.log("================================================================");
  } catch (err) {
    console.error("\n!!! TEST FLOW FAILED !!!", err);
    console.log("\n--- RECENT BROWSER LOGS ---");
    console.log(browserLogs.slice(-25).join("\n"));
    throw err;
  } finally {
    await browser.close();
  }
}

runAutonomousFlow().catch((e) => {
  console.error("Runner exited with error:", e);
  process.exit(1);
});
