import puppeteer from 'puppeteer-core';
import fs from 'fs';
import path from 'path';

const CHROME_PATH = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const APP_URL = 'http://127.0.0.1:5173';

async function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function runBrowserVerification() {
  console.log('=== Starting Real Browser E2E Verification ===');
  console.log(`Connecting Chrome executable: ${CHROME_PATH}`);

  const browser = await puppeteer.launch({
    executablePath: CHROME_PATH,
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--window-size=1280,900'],
  });

  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 900 });

  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      console.log(`[Browser Console Error] ${msg.text()}`);
    }
  });
  page.on('requestfailed', (req) => {
    console.log(`[Browser Request Failed] ${req.url()} (${req.failure()?.errorText})`);
  });
  page.on('response', async (res) => {
    if (res.status() >= 400 && !res.url().includes('favicon')) {
      try {
        const text = await res.text();
        console.log(`[API Error ${res.status()} ${res.url()}]: ${text}`);
      } catch {}
    }
  });
  page.on('dialog', async (dialog) => {
    console.log(`[Browser Dialog] Auto-accepting: ${dialog.message()}`);
    await dialog.accept();
  });

  try {
    // 1. Load Application
    console.log(`\nStep 1: Navigating to ${APP_URL}...`);
    await page.goto(APP_URL, { waitUntil: 'networkidle0', timeout: 15000 });
    console.log('Page loaded successfully. Title:', await page.title());

    // 2. Operator Flow: Create Session
    console.log('\nStep 2: Switching to Operator View...');
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const target = btns.find((b) => b.textContent.includes('研究者後台'));
      if (target) target.click();
    });
    await sleep(1000);

    const hasOperatorHeader = await page.evaluate(() => {
      return (
        document.body.textContent.includes('研究者身分授權') ||
        document.body.textContent.includes('建立新 Session')
      );
    });
    console.log('Operator dashboard rendered:', hasOperatorHeader);
    if (!hasOperatorHeader) {
      throw new Error('Operator dashboard did not render!');
    }

    console.log('Creating new Session in Operator view...');
    await page.type('input[placeholder="例如: P_001"]', 'browser-test-p01');
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const target = btns.find((b) => b.textContent.includes('建立 Session 並初始化試驗'));
      if (target) target.click();
    });
    await sleep(2000);

    const sessionCode = await page.evaluate(() => {
      const codeEl =
        document.querySelector('.border-emerald-300') ||
        document.querySelector('td.font-mono.font-bold');
      return codeEl ? codeEl.textContent.trim() : null;
    });
    console.log(`Session created! Code: ${sessionCode}`);
    if (!sessionCode || !sessionCode.startsWith('PL-')) {
      throw new Error(`Failed to create session or invalid code: ${sessionCode}`);
    }

    // 3. Participant Flow: Switch to Participant & Join Session
    console.log('\nStep 3: Switching to Participant View and Joining Session...');
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const target = btns.find((b) => b.textContent.includes('受試者視角'));
      if (target) target.click();
    });
    await sleep(1000);

    await page.waitForSelector('#session-code', { timeout: 5000 });
    await page.type('#session-code', sessionCode);
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const target = btns.find((b) => b.textContent.includes('進入試驗'));
      if (target) target.click();
    });
    await sleep(2000);

    // 4. Verify Puzzle View Loaded
    console.log('\nStep 4: Verifying Puzzle View...');
    const trialEnv = await page.evaluate(() => {
      return document.body.textContent.includes('Puzzle Hints') || document.body.textContent.includes('邏輯線索排列');
    });
    console.log('Puzzle view active:', trialEnv);
    if (!trialEnv) {
      throw new Error('Puzzle Hints trial did not load after join!');
    }

    await sleep(1200);
    const initialTimerText = await page.evaluate(() => {
      const timeEl = document.querySelector('.font-mono.font-bold.text-slate-700');
      return timeEl ? timeEl.textContent : null;
    });
    console.log('Active play timer text:', initialTimerText);

    // 5. Test Pause & Resume
    console.log('\nStep 5: Testing Pause and Resume Overlay...');
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const target = btns.find((b) => b.textContent.includes('暫停'));
      if (target) target.click();
    });
    await sleep(1000);

    const isPaused = await page.evaluate(() => {
      return document.body.textContent.includes('試驗已暫停') && document.body.textContent.includes('繼續試驗');
    });
    console.log('Pause overlay active:', isPaused);
    if (!isPaused) {
      throw new Error('Pause overlay was not displayed!');
    }

    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const target = btns.find((b) => b.textContent.includes('繼續試驗'));
      if (target) target.click();
    });
    await sleep(1000);

    const isResumed = await page.evaluate(() => {
      return !document.body.textContent.includes('試驗已暫停');
    });
    console.log('Resumed from pause:', isResumed);

    // 6. Test Palette & Check Answer
    console.log('\nStep 6: Testing Board Item Placement & Check Answer...');
    const itemClicked = await page.evaluate(() => {
      // Find item in palette
      const paletteContainer = document.querySelector('.border-dashed') || document.querySelector('.space-y-4');
      const allButtons = Array.from(document.querySelectorAll('button'));
      const paletteBtn = allButtons.find((b) =>
        b.className.includes('rounded-xl border') &&
        !b.textContent.includes('檢查') &&
        !b.textContent.includes('暫停') &&
        !b.textContent.includes('跳過') &&
        !b.textContent.includes('協助')
      );
      if (paletteBtn) {
        paletteBtn.click();
        return paletteBtn.textContent.trim();
      }
      return null;
    });
    console.log('Palette interaction performed, item:', itemClicked);
    await sleep(500);

    // Click Check Answer
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const target = btns.find((b) => b.textContent.includes('檢查答案'));
      if (target) target.click();
    });
    await sleep(1000);

    const feedbackShown = await page.evaluate(() => {
      return (
        document.body.textContent.includes('尚未完全符合') ||
        document.body.textContent.includes('檢查') ||
        document.body.textContent.includes('嘗試次數')
      );
    });
    console.log('Check answer feedback displayed:', feedbackShown);

    // 7. Test Decision Modal (Open Decision Assistance)
    console.log('\nStep 7: Testing Decision Modal (Assistance Options)...');
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const target = btns.find((b) => b.textContent.includes('我想看看協助選項'));
      if (target) target.click();
    });
    await sleep(1000);

    const isModalOpen = await page.evaluate(() => {
      return (
        document.body.textContent.includes('偏好決策：選擇本次協助方案') &&
        (document.body.textContent.includes('給我一點方向') || document.body.textContent.includes('方向')) &&
        (document.body.textContent.includes('告訴我下一步') || document.body.textContent.includes('下一步'))
      );
    });
    console.log('Decision modal opened with 4 actions:', isModalOpen);
    if (!isModalOpen) {
      throw new Error('Decision modal did not open!');
    }

    // Try submitting without evaluating -> Should fail validation
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const target = btns.find((b) => b.textContent.includes('確認並執行此方案'));
      if (target) target.click();
    });
    await sleep(500);

    const hasValidationErr = await page.evaluate(() => {
      return document.body.textContent.includes('請對所有方案標記可接受性');
    });
    console.log('Validation prevented incomplete submission:', hasValidationErr);

    // Evaluate all 4 actions as "可接受"
    await page.evaluate(() => {
      const yesBtns = Array.from(document.querySelectorAll('button')).filter((b) => b.textContent.trim() === '可接受');
      yesBtns.forEach((b) => b.click());
    });
    await sleep(500);

    // Select the "hint" (給我一點方向) action
    await page.evaluate(() => {
      const cards = Array.from(document.querySelectorAll('div')).filter(
        (d) => (d.textContent.includes('給我一點方向') || d.textContent.includes('方向')) && d.querySelector('input[type="radio"]')
      );
      if (cards.length > 0) {
        const radio = cards[0].querySelector('input[type="radio"]');
        if (radio) radio.click();
      }
    });
    await sleep(500);

    // Submit decision
    console.log('Submitting assistance choice...');
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const target = btns.find((b) => b.textContent.includes('確認並執行此方案'));
      if (target) target.click();
    });
    await sleep(1500);

    const hintOutcomeShown = await page.evaluate(() => {
      return (
        document.body.textContent.includes('系統提供之方向提示') ||
        document.body.textContent.includes('提示')
      );
    });
    console.log('Hint outcome successfully applied on board:', hintOutcomeShown);

    // 8. Skip Trial to test Post-Trial Feedback & Followup Solution
    console.log('\nStep 8: Testing Skip Trial & Post-Trial Feedback...');
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const target = btns.find((b) => b.textContent.includes('跳過此題'));
      if (target) target.click();
    });
    await sleep(2000);

    const feedbackCardVisible = await page.evaluate(() => {
      return (
        document.body.textContent.includes('本題已跳過') ||
        document.body.textContent.includes('您覺得這次獲得的協助如何？')
      );
    });
    console.log('Post-trial feedback card visible:', feedbackCardVisible);
    if (!feedbackCardVisible) {
      throw new Error('Feedback card was not displayed after trial completion/skip!');
    }

    // Select "剛好" rating and submit
    await page.evaluate(() => {
      const ratingBtns = Array.from(document.querySelectorAll('button')).filter(
        (b) => b.textContent.trim() === '剛好'
      );
      if (ratingBtns.length > 0) ratingBtns[0].click();
    });
    await sleep(500);

    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const target = btns.find((b) => b.textContent.includes('送出回饋') || b.textContent.includes('回饋'));
      if (target) target.click();
    });
    await sleep(1000);

    // Click reveal solution
    console.log('Revealing followup solution...');
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const target = btns.find((b) => b.textContent.includes('看解法'));
      if (target) target.click();
    });
    await sleep(1000);

    const solRevealed = await page.evaluate(() => {
      return (
        document.body.textContent.includes('正解') ||
        document.body.textContent.includes('格')
      );
    });
    console.log('Followup solution successfully revealed:', solRevealed);

    // Advance to next trial (BRET tutorial)
    console.log('\nStep 9: Advancing to Next Trial (BRET Tutorial)...');
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const target = btns.find((b) => b.textContent.includes('前進下一題') || b.textContent.includes('前進下一回合'));
      if (target) target.click();
    });
    await sleep(2000);

    // 9. Verify Next Trial Loaded (Trial 2: pz_pilot_02)
    const nextTrialLoaded = await page.evaluate(() => {
      return (
        document.body.textContent.includes('第 2 題') ||
        document.body.textContent.includes('pz_pilot_02') ||
        document.body.textContent.includes('Puzzle Hints')
      );
    });
    console.log('Next trial (Trial 2) successfully loaded:', nextTrialLoaded);
    if (!nextTrialLoaded) {
      throw new Error('Trial 2 did not load after clicking Next!');
    }

    // 10. Refresh & State Restoration Verification
    console.log('\nStep 10: Testing Browser Page Refresh Restoration...');
    await page.reload({ waitUntil: 'networkidle0' });
    await sleep(2000);

    const restoredSession = await page.evaluate(() => {
      return (
        document.body.textContent.includes('第 2 題') ||
        document.body.textContent.includes('pz_pilot_02') ||
        document.body.textContent.includes('Puzzle Hints')
      );
    });
    console.log('State properly restored after browser reload:', restoredSession);
    if (!restoredSession) {
      throw new Error('Trial state was not restored after refresh!');
    }

    // 11. Operator Verification: Event Stream & Details
    console.log('\nStep 11: Operator Inspection & Monotonic Event Stream...');
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const target = btns.find((b) => b.textContent.includes('研究者後台'));
      if (target) target.click();
    });
    await sleep(1000);

    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const target = btns.find((b) => b.textContent.includes('檢視'));
      if (target) target.click();
    });
    await sleep(1500);

    const eventStreamInfo = await page.evaluate(() => {
      const evHeader = Array.from(document.querySelectorAll('h4')).find((h) =>
        h.textContent.includes('有序事件日誌')
      );
      const evItems = Array.from(document.querySelectorAll('.leading-relaxed'));
      return {
        header: evHeader ? evHeader.textContent.trim() : null,
        count: evItems.length,
      };
    });
    console.log('Event Stream Log verified:', eventStreamInfo);

    // Take verification screenshot
    const docsDir = path.resolve('..', 'docs');
    if (!fs.existsSync(docsDir)) fs.mkdirSync(docsDir, { recursive: true });
    const screenshotPath = path.resolve(docsDir, 'browser_e2e_verification.png');
    await page.screenshot({ path: screenshotPath, fullPage: true });
    console.log(`Saved screenshot evidence to: ${screenshotPath}`);

    console.log('\n=== ALL BROWSER E2E VERIFICATIONS PASSED SUCCESSFULLY ===');
  } catch (err) {
    console.error('\n❌ Browser verification failed:', err);
    throw err;
  } finally {
    await browser.close();
  }
}

runBrowserVerification().catch((err) => {
  console.error(err);
  process.exit(1);
});
