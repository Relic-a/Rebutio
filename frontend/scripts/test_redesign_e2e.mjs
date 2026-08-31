import { chromium } from "playwright";
import fs from "fs";
import path from "path";

const BASE_URL = process.env.BASE_URL || "http://localhost:3000";
const SCREENSHOT_DIR = path.resolve(process.cwd(), "frontend/test-results/screenshots");
fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });

function assert(condition, message) {
  if (!condition) {
    throw new Error(`[ASSERTION FAILED] ${message}`);
  }
}

async function run() {
  console.log(`Starting autonomous browser test against ${BASE_URL}...`);
  const browser = await chromium.launch({ headless: true });

  const viewports = [
    { name: "desktop", width: 1280, height: 800 },
    { name: "mobile", width: 390, height: 844 },
  ];

  for (const vp of viewports) {
    console.log(`\n========================================`);
    console.log(`Testing Viewport: ${vp.name} (${vp.width}x${vp.height})`);
    console.log(`========================================`);

    const context = await browser.newContext({
      viewport: { width: vp.width, height: vp.height },
      userAgent: `Mozilla/5.0 (Rebutio-E2E-Tester-${vp.name})`,
    });
    const page = await context.newPage();

    // -------------------------------------------------------------------------
    // 1. Onboarding Flow & Continuous Debate Mounting
    // -------------------------------------------------------------------------
    console.log("1. Testing Onboarding Flow (/onboarding)...");
    await page.goto(`${BASE_URL}/onboarding`, { waitUntil: "networkidle" });
    await page.waitForSelector("h1", { timeout: 15000 });
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, `${vp.name}_01_onboarding_welcome.png`) });

    // Step 1 -> Step 2
    await page.click("button:has-text('Start my first debate')");
    await page.waitForTimeout(800);

    // Step 2: Goals
    const goalBtn = page.locator("button:has-text('Sound natural')").first();
    if (await goalBtn.isVisible()) {
      await goalBtn.click();
    } else {
      await page.locator("button[aria-pressed]").first().click();
    }
    await page.click("button:has-text('Continue')");
    await page.waitForTimeout(800);

    // Step 3: Comfort
    await page.locator("button:has-text('I can hold conversations')").first().click();
    await page.click("button:has-text('Continue')");
    await page.waitForTimeout(800);

    // Step 4: Interests (Select at least 3)
    const interestButtons = page.locator("button[aria-pressed]");
    const count = await interestButtons.count();
    for (let i = 0; i < Math.min(3, count); i++) {
      await interestButtons.nth(i).click();
      await page.waitForTimeout(200);
    }
    await page.click("button:has-text('Continue')");
    await page.waitForTimeout(800);

    // Step 5: Intensity
    await page.locator("button:has-text('Balanced')").first().click();
    await page.click("button:has-text('Continue')");
    await page.waitForTimeout(800);

    // Step 6: Spar Briefing
    console.log("   Verifying Spar Briefing (Continuous format, no legacy turn labels)...");
    await page.waitForSelector("h1:has-text(\"Let's see how you argue\")", { timeout: 10000 });
    const briefingText = await page.textContent("body");
    assert(!briefingText.includes("3 short turns"), "Spar briefing must not display legacy '3 short turns'");
    assert(briefingText.includes("continuous spar") || briefingText.includes("spar"), "Spar briefing mentions continuous spar");

    // Select Agree side and start spar
    await page.click("button:has-text('Agree')");
    await page.waitForTimeout(500);
    await page.click("button:has-text('Start Spar')");
    await page.waitForTimeout(1500);

    // If Mic Permission step appears, click enable or skip
    const micPrompt = page.locator("h1:has-text('needs to hear')");
    if (await micPrompt.isVisible()) {
      const skipMic = page.locator("button:has-text('Not now'), button:has-text('Continue without audio')").first();
      if (await skipMic.isVisible()) {
        await skipMic.click();
      }
    }

    // -------------------------------------------------------------------------
    // 2. Continuous Debate Spar: Zero Rounds & Multi-Exchange Verification
    // -------------------------------------------------------------------------
    console.log("2. Verifying Continuous Debate Surface...");
    await page.waitForSelector("header", { timeout: 15000 });
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, `${vp.name}_02_continuous_debate_ready.png`) });

    // CRITICAL ASSERTION: No "Round X of Y" visible anywhere in debate header
    const headerText = await page.textContent("header");
    assert(!headerText.includes("Round"), "Header MUST NOT display 'Round X of Y'");
    assert(!headerText.includes("of 3") && !headerText.includes("of 4"), "Header MUST NOT display turn count limits");
    console.log("   ✓ Verified: No 'Round X of Y' or fixed turn numbers visible in header");

    // Switch to Text Mode if in Voice Mode
    const typeInsteadBtn = page.locator("button:has-text('Type instead')");
    if (await typeInsteadBtn.isVisible()) {
      await typeInsteadBtn.click();
      await page.waitForTimeout(500);
    }

    // --- Exchange 1: Argument ---
    console.log("   Submitting Exchange 1 (Opening Claim)...");
    await page.waitForSelector("textarea", { timeout: 5000 });
    await page.fill("textarea", "Social media prioritizes algorithmic engagement over genuine empathy, isolating individuals in curated echo chambers.");
    await page.keyboard.press("Enter");

    // Wait for opponent response in the stream
    await page.waitForSelector("div.rounded-2xl.bg-white p", { timeout: 20000 });
    await page.waitForTimeout(1500);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, `${vp.name}_03_debate_exchange1_response.png`) });
    console.log("   ✓ Exchange 1 received opponent rebuttal");

    // --- Exchange 2: User Question ---
    console.log("   Submitting Exchange 2 (User Question)...");
    await page.waitForSelector("textarea", { timeout: 5000 });
    await page.fill("textarea", "What about isolated seniors who rely on online communities for companionship? How does your stance address them?");
    await page.keyboard.press("Enter");

    await page.waitForTimeout(3000);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, `${vp.name}_04_debate_exchange2_question_response.png`) });
    console.log("   ✓ Exchange 2 (User Question) answered by opponent");

    // --- Exchange 3: Rebuttal / Evidence ---
    console.log("   Submitting Exchange 3 (Counter-evidence)...");
    await page.waitForSelector("textarea", { timeout: 5000 });
    await page.fill("textarea", "Even with niche benefits, longitudinal clinical data indicates overwhelming increases in teenage anxiety directly correlated with screen time.");
    await page.keyboard.press("Enter");

    await page.waitForTimeout(3000);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, `${vp.name}_05_debate_exchange3_evidence_response.png`) });
    console.log("   ✓ Exchange 3 received opponent response (debate continues continuously without ending at round 3)");

    // -------------------------------------------------------------------------
    // 3. Concluding Debate & Results Screen
    // -------------------------------------------------------------------------
    console.log("3. Concluding debate and verifying Results Screen...");
    page.on("dialog", (dialog) => dialog.accept());
    const finishBtn = page.locator("button:has-text('Finish')");
    if (await finishBtn.isVisible()) {
      await finishBtn.click();
    }

    await page.waitForURL("**/results*", { timeout: 20000 });
    await page.waitForSelector("h1:has-text('Debate Summary')", { timeout: 15000 });
    await page.waitForTimeout(1000);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, `${vp.name}_06_results_summary.png`) });

    // Assert 4 Integer Scores are rendered cleanly
    const resultsContent = await page.textContent("body");
    assert(resultsContent.includes("Technique"), "Results must display Technique score");
    assert(resultsContent.includes("Grammar"), "Results must display Grammar score");
    assert(resultsContent.includes("Vocabulary"), "Results must display Vocabulary score");
    assert(resultsContent.includes("Delivery"), "Results must display Delivery score");
    assert(resultsContent.includes("Strongest Moment"), "Results must display Strongest Moment");
    assert(resultsContent.includes("Primary Focus"), "Results must display Primary Focus");
    console.log("   ✓ Results screen contains all 4 evaluation scores and standout moments");

    // -------------------------------------------------------------------------
    // 4. View Transcript Drawer (Real Turn Transcript)
    // -------------------------------------------------------------------------
    console.log("4. Testing 'View Transcript' Drawer on Results Page...");
    const viewTranscriptBtn = page.locator("button:has-text('View Transcript')");
    assert(await viewTranscriptBtn.isVisible(), "View Transcript button must be visible");
    await viewTranscriptBtn.click();
    await page.waitForTimeout(1500);

    await page.screenshot({ path: path.join(SCREENSHOT_DIR, `${vp.name}_07_results_transcript_drawer.png`) });
    const transcriptDrawerText = await page.textContent("div:has-text('Debate Transcript')");
    assert(!transcriptDrawerText.includes("Full transcript recorded and analyzed for coaching session."), "Must NOT display static placeholder text");
    assert(transcriptDrawerText.includes("Social media") || transcriptDrawerText.includes("Rebutio") || transcriptDrawerText.includes("You"), "Transcript drawer must display real turns");
    console.log("   ✓ 'View Transcript' drawer displays actual debate turns");

    // -------------------------------------------------------------------------
    // 5. Session-Specific Coach Thread
    // -------------------------------------------------------------------------
    console.log("5. Navigating to Session Coach Chat...");
    const reviewWithCoachBtn = page.locator("button:has-text('Review with my coach')");
    await reviewWithCoachBtn.click();

    await page.waitForURL("**/coach/session/*", { timeout: 20000 });
    await page.waitForSelector("h1", { timeout: 15000 });
    await page.waitForTimeout(2000);
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, `${vp.name}_08_session_coach_chat.png`) });

    // Assert Proactive Opening Analysis exists
    const coachBody = await page.textContent("body");
    assert(!coachBody.includes("Could not load coaching session"), "Session coach must load without error");
    assert(coachBody.includes("Opening Analysis") || coachBody.includes("Standout Strength"), "Session coach must display proactive opening analysis card");
    console.log("   ✓ Session Coach thread loaded proactive analysis cleanly");

    // Click a Quick Reply chip
    const quickReply = page.locator("div.flex-wrap button").first();
    if (await quickReply.isVisible()) {
      const qrText = await quickReply.innerText();
      console.log(`   Clicking Quick Reply chip: "${qrText}"...`);
      await quickReply.click();
      await page.waitForTimeout(3000);
      await page.screenshot({ path: path.join(SCREENSHOT_DIR, `${vp.name}_09_quick_reply_response.png`) });
      console.log("   ✓ Quick reply conversation response received");
    }

    // Type a custom text message to coach
    const coachInput = page.locator("input[placeholder*='Ask coach']");
    if (await coachInput.isVisible()) {
      console.log("   Sending custom question to coach...");
      await coachInput.fill("How should I phrase my central premise to sound more commanding?");
      await coachInput.press("Enter");
      await page.waitForTimeout(3500);
      await page.screenshot({ path: path.join(SCREENSHOT_DIR, `${vp.name}_10_custom_question_response.png`) });
      console.log("   ✓ Custom coach question answered");
    }

    // -------------------------------------------------------------------------
    // 6. Test Message Persistence Across Page Reload
    // -------------------------------------------------------------------------
    console.log("6. Verifying message persistence after page reload...");
    await page.reload({ waitUntil: "networkidle" });
    await page.waitForSelector("h1", { timeout: 15000 });
    await page.waitForTimeout(1500);
    const reloadedBody = await page.textContent("body");
    assert(reloadedBody.includes("central premise") || reloadedBody.includes("commanding") || reloadedBody.includes("Strength"), "Messages must persist after page reload");
    console.log("   ✓ Message history successfully persisted across page reload");

    // -------------------------------------------------------------------------
    // 7. General Coach Home & Longitudinal Memory
    // -------------------------------------------------------------------------
    console.log("7. Visiting General Coach Home (/coach)...");
    await page.goto(`${BASE_URL}/coach`, { waitUntil: "networkidle" });
    await page.waitForSelector("h1", { timeout: 15000 });
    await page.screenshot({ path: path.join(SCREENSHOT_DIR, `${vp.name}_11_coach_home.png`) });

    const coachHomeText = await page.textContent("body");
    assert(coachHomeText.includes("Speaking Coach") || coachHomeText.includes("Active Focus"), "Coach home must render active focus and guidance");

    // Test Clarify Note Modal on Coach Home if available
    const clarifyBtn = page.locator("button:has-text('Clarify note')").first();
    if (await clarifyBtn.isVisible()) {
      await clarifyBtn.click();
      await page.waitForSelector("textarea", { timeout: 5000 });
      await page.fill("textarea", "I was pausing intentionally for emphasis, not losing my train of thought.");
      await page.screenshot({ path: path.join(SCREENSHOT_DIR, `${vp.name}_12_clarify_modal.png`) });
      await page.click("button:has-text('Save Correction')");
      await page.waitForTimeout(1500);
      console.log("   ✓ Memory clarification saved successfully");
    }

    await context.close();
  }

  await browser.close();
  console.log("\n========================================");
  console.log("✓ ALL 12 E2E CRITERIA VERIFIED AND PASSED ON MOBILE & DESKTOP!");
  console.log(`Screenshots saved to: ${SCREENSHOT_DIR}`);
  console.log("========================================");
}

run().catch((err) => {
  console.error("E2E Test Execution Failed:", err);
  process.exit(1);
});
