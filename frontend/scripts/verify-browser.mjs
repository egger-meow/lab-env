import puppeteer from 'puppeteer-core';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { spawn, execFileSync } from 'node:child_process';
const APP = process.env.APP_URL || 'http://127.0.0.1:18731', API = process.env.API_URL || 'http://127.0.0.1:18732';
const out = path.resolve('../runs/part-c/browser');
fs.mkdirSync(out, { recursive: true });
const checks = [], errors = [], payloads = [];
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
// Keep local servers and Chrome in the same host execution context.
const database = path.join(out, `synthetic-${Date.now()}.sqlite3`);
const backend = spawn(path.resolve('../backend/.venv/Scripts/python.exe'), ['-m', 'uvicorn', 'preference_lab.api.app:app', '--host', '127.0.0.1', '--port', new URL(API).port], {
    cwd: path.resolve('../backend'), windowsHide: true,
    env: { ...process.env, PREFERENCE_LAB_DB: database, PREFERENCE_LAB_DECISION_SOURCE: 'synthetic_mock' }, stdio: ['ignore', 'ignore', 'pipe'],
});
const frontend = spawn(process.execPath, ['node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', new URL(APP).port, '--strictPort'], {
    cwd: process.cwd(), windowsHide: true, env: { ...process.env, PREFERENCE_LAB_API_URL: API }, stdio: ['ignore', 'ignore', 'pipe'],
});
backend.stderr.on('data', data => { if (String(data).includes('ERROR'))
    console.error(String(data)); });
frontend.stderr.on('data', data => console.error(String(data)));
process.on('exit', () => { backend.kill(); frontend.kill(); });
for (let attempt = 0; attempt < 40; attempt++) {
    if (backend.exitCode !== null || frontend.exitCode !== null)
        throw new Error('Isolated test server exited; refusing to use an existing service');
    try {
        const responses = await Promise.all([fetch(API + '/api/health'), fetch(APP)]);
        if (responses.every(r => r.ok))
            break;
    }
    catch { /* wait for startup */ }
    await sleep(250);
}
const browser = await puppeteer.launch({ executablePath: process.env.CHROME_PATH || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe', headless: true, userDataDir: path.join(out, `profile-${Date.now()}`), args: ['--no-sandbox', '--window-size=1280,720'] });
const page = await browser.newPage();
await page.setViewport({ width: 1280, height: 720 });
page.on('pageerror', err => errors.push(err.message));
page.on('dialog', dialog => dialog.accept());
page.on('request', req => { if (req.url().endsWith('/decision') && req.method() === 'POST')
    payloads.push(req.postData()); });
const check = (value, text) => { assert.ok(value, text); checks.push(text); console.log('PASS', text); };
const shot = name => page.screenshot({ path: path.join(out, `${name}.png`) });
async function click(text) {
    await page.locator(`xpath///button[contains(., ${JSON.stringify(text)}) and not(@disabled)]`).click();
}
async function api(url, body, token) {
    const r = await fetch(API + url, { method: body ? 'POST' : 'GET', headers: { 'Content-Type': 'application/json', ...(token ? { 'X-Session-Token': token } : { 'X-Operator-Token': 'dev-operator-token-local' }) }, body: body ? JSON.stringify(body) : undefined });
    assert.ok(r.ok, `${url}: ${r.status} ${!r.ok ? await r.text() : ''}`);
    return r.json();
}
let token, code, id;
const current = () => api(`/api/trials/${id}`, null, token);
async function status(expected, timeout = 15000) { const end = Date.now() + timeout; while (Date.now() < end) {
    const t = await current();
    if (t.status === expected)
        return t;
    await sleep(150);
} throw new Error(`Expected ${expected}, got ${(await current()).status}`); }
async function blank(t, name) {
    assert.deepEqual(await page.$$eval(`input[name="${name}"]`, els => els.map(i => i.value)), t.display_order);
    check(true, `${t.item_id}: display_order`);
    check(await page.$$eval(`input[name="${name}"]:checked`, els => !els.length), `${t.item_id}: blank choice`);
    check(await page.$$eval('button[aria-pressed="true"]', els => !els.length), `${t.item_id}: blank acceptability`);
    check(await page.$$eval('textarea, #reason', els => els.every(i => i.value === '')), `${t.item_id}: blank reason`);
}
async function fill(name, action) { const ratings = await page.$$('button[aria-pressed]'); for (let i = 0; i < ratings.length; i += 3)
    await ratings[i].click(); await page.click(`input[name="${name}"][value="${action}"]`); }
async function locked(name, reasonSelector, expectedReason, expectedChoice, screenshot) {
    await page.waitForFunction(() => document.body.textContent.includes('提交結果尚未確認'));
    check(await page.$eval(`input[name="${name}"]`, el => el.matches(':disabled')), `${name}: pending choice locked`);
    check(await page.$eval(reasonSelector, el => el.matches(':disabled')), `${name}: pending reason locked`);
    check(await page.$$eval('button[aria-pressed]', els => els.every(el => el.matches(':disabled'))), `${name}: pending ratings locked`);
    await page.click(`input[name="${name}"]:not([value="${expectedChoice}"])`);
    await page.focus(reasonSelector);
    await page.keyboard.type('changed answer must not apply');
    check(await page.$eval(reasonSelector, (el, reason) => el.value === reason, expectedReason), `${name}: pending original reason displayed`);
    check(await page.$eval(`input[name="${name}"][value="${expectedChoice}"]`, el => el.checked), `${name}: pending original selection displayed`);
    check(await page.$$eval('button', els => els.some(el => el.textContent.includes('重試原提交') && !el.disabled)), `${name}: explicit original retry available`);
    await shot(screenshot);
}
async function externalVersionChange() {
    const before = await current();
    const paused = await api(`/api/trials/${id}/pause`, { active_play_ms: before.active_play_ms, state_version: before.state_version }, token);
    await api(`/api/trials/${id}/resume`, { state_version: paused.state_version }, token);
}
async function next(text) {
    const response = page.waitForResponse(r => r.url().endsWith('/next') && r.request().method() === 'POST');
    await click(text);
    const result = await (await response).json();
    assert.ok(result.has_next && result.next_trial_id, 'Next trial response');
    id = result.next_trial_id;
    const trial = await current();
    await page.waitForFunction(itemId => document.body.textContent.includes(itemId), {}, trial.item_id);
}
try {
    await page.goto(APP + '?view=operator', { waitUntil: 'networkidle0' });
    check(await page.$('input[placeholder="例如: P_001"]'), '?view=operator entry');
    await shot('operator');
    await page.type('input[placeholder="例如: P_001"]', 'llm_synthetic_part_c_e2e');
    const creation = page.waitForResponse(r => r.url().endsWith('/api/operator/sessions') && r.request().method() === 'POST');
    await click('建立 Session 並初始化試驗');
    const creationResponse = await creation;
    check(creationResponse.ok(), 'Operator creates session through UI');
    const created = await creationResponse.json();
    await page.waitForFunction(() => document.body.textContent.includes('建立成功'));
    await shot('operator-created');

    // Two independent browser windows use the real client with the same captured version.
    const conflictSession = await api('/api/operator/sessions', { participant_id: 'llm_synthetic_two_windows' });
    const conflictJoin = await api('/api/sessions/join', { session_code: conflictSession.session.session_code });
    const other = await browser.newPage();
    await other.goto(APP);
    const args = [conflictJoin.current_trial_id, conflictJoin.session_token];
    const initial = await api(`/api/trials/${args[0]}`, null, args[1]);
    const newBoard = [initial.public_stimulus.items[0], null, null, null];
    await page.evaluate(async ([id, token, board, version]) => {
      const { api } = await import('/src/api/client.ts');
      await api.updateBoard(id, board, 0, version, token);
    }, [...args, newBoard, initial.state_version]);
    await page.evaluate(async ([id, token]) => {
      const { api } = await import('/src/api/client.ts');
      let trial = await api.getTrial(id, token);
      while (trial.state_version < 9) {
        await api.checkpoint(id, 0, trial.state_version, token);
        trial = await api.getTrial(id, token);
      }
      if (trial.state_version !== 9) throw new Error('Expected server version 9');
    }, args);
    check(initial.state_version === 1, 'Two-window counterexample captures version 1 against server version 9');
    for (const operation of ['board', 'check-answer']) {
      const rejected = await other.evaluate(async ([id, token, version, operation]) => {
        const { api } = await import('/src/api/client.ts');
        let synchronized;
        window.addEventListener('preference-lab-conflict', e => { synchronized = e.detail; }, { once: true });
        try {
          if (operation === 'board') await api.updateBoard(id, [null, null, null, null], 0, version, token);
          else await api.checkAnswer(id, 0, version, [null, null, null, null], token);
          return { rejected: false };
        } catch (error) { return { rejected: error.isStateVersionConflict, synchronized }; }
      }, [...args, initial.state_version, operation]);
      check(rejected.rejected, `Second window stale ${operation} rejected`);
      assert.deepEqual(rejected.synchronized.public_state.board, newBoard);
      const preserved = await api(`/api/trials/${args[0]}`, null, args[1]);
      assert.deepEqual(preserved.public_state.board, newBoard);
      check(preserved.public_state.attempts === initial.public_state.attempts, `Stale ${operation} preserves board and attempts`);
    }
    const local = await api(`/api/trials/${args[0]}`, null, args[1]);
    await other.evaluate(async ([id, token, version, board]) => {
      const { api } = await import('/src/api/client.ts');
      await Promise.all([api.checkpoint(id, 0, version, token), api.updateBoard(id, board, 0, version, token)]);
    }, [...args, local.state_version, newBoard]);
    check(true, 'Confirmed local queued predecessor advances only its own chain');
    const interleave = await api(`/api/trials/${args[0]}`, null, args[1]);
    const protectedBoard = [null, interleave.public_stimulus.items[0], null, null];
    const refused = await other.evaluate(async ([id, token, version, protectedBoard]) => {
        const { api } = await import('/src/api/client.ts');
        const originalFetch = window.fetch;
        window.fetch = async (...args) => {
            const response = await originalFetch(...args);
            if (String(args[0]).endsWith('/checkpoint') && response.ok) {
                const checkpoint = await response.clone().json();
                const external = await originalFetch(`/api/trials/${id}/board`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Session-Token': token }, body: JSON.stringify({ board: protectedBoard, active_play_ms: 0, state_version: checkpoint.state_version }) });
                if (!external.ok) throw new Error('External intervening write failed');
            }
            return response;
        };
        try {
            const results = await Promise.allSettled([api.checkpoint(id, 0, version, token), api.updateBoard(id, [null, null, null, null], 0, version, token)]);
            return results[0].status === 'fulfilled' && results[1].status === 'rejected' && results[1].reason.isStateVersionConflict;
        } finally { window.fetch = originalFetch; }
    }, [...args, interleave.state_version, protectedBoard]);
    check(refused, 'External write between local queued commands remains a conflict');
    assert.deepEqual((await api(`/api/trials/${args[0]}`, null, args[1])).public_state.board, protectedBoard);
    await other.close();
    await page.bringToFront();
    code = created.session.session_code;
    const joined = await api('/api/sessions/join', { session_code: code });
    token = joined.session_token;
    id = joined.current_trial_id;
    await page.goto(APP);
    await page.waitForSelector('#session-code');
    await page.type('#session-code', code);
    await click('進入試驗');
    await page.waitForFunction(() => document.body.textContent.includes('邏輯位置排列謎題'));
    check((await current()).active_play_ms < 1000, 'First puzzle timer starts at zero');
    check(await page.evaluate(() => document.body.textContent.includes('月亮')), 'Chinese labels and clues');
    await shot('participant-puzzle');
    await sleep(5600);
    check((await current()).active_play_ms >= 5000, 'Timer heartbeat without board actions');
    const beforeReloadSeconds = await page.evaluate(() => Math.max(...[...document.querySelectorAll('span')].map(el => /^\d+ 秒$/.test(el.textContent) ? parseInt(el.textContent) : 0)));
    await page.reload({ waitUntil: 'networkidle0' });
    check(await page.evaluate(before => [...document.querySelectorAll('span')].some(el => /^\d+ 秒$/.test(el.textContent) && parseInt(el.textContent) >= before), beforeReloadSeconds), 'Active reload preserves visible unsaved time');
    const away = await browser.newPage();
    await away.bringToFront();
    await status('paused');
    await page.bringToFront();
    await away.close();
    await page.waitForFunction(() => document.body.textContent.includes('試驗已暫停'));
    const pausedMs = (await current()).active_play_ms;
    await shot('paused');
    await sleep(700);
    check((await current()).active_play_ms === pausedMs, 'Blur calls pause and freezes time');
    await page.reload({ waitUntil: 'networkidle0' });
    check((await current()).status === 'paused', 'Reload preserves pause');
    await click('繼續');
    console.log('Waiting for real 45-second primary threshold');
    await status('decision_open', 50000);
    await page.waitForSelector('[role="dialog"]');
    let t = await current();
    check(t.active_play_ms >= 45000 && t.active_play_ms < 47000, '45 seconds automatically opens primary decision');
    await blank(t, 'selected_action');
    await shot('decision-modal');
    await fill('selected_action', 'continue');
    await page.type('#reason', 'synthetic retry evidence');
    await page.reload({ waitUntil: 'networkidle0' });
    await page.waitForSelector('#reason');
    check(await page.$eval('#reason', i => i.value === 'synthetic retry evidence'), 'Puzzle draft survives reload');
    check(await page.$eval('input[value="continue"]', i => i.checked), 'Puzzle choice survives reload');
    assert.deepEqual(await page.$$eval('input[name=selected_action]', els => els.map(el => el.value)), t.display_order);
    check(true, 'Puzzle order survives reload');
    await page.focus('[role="dialog"] button');
    await page.keyboard.down('Shift');
    await page.keyboard.press('Tab');
    await page.keyboard.up('Shift');
    check(await page.evaluate(() => !!document.activeElement.closest('[role="dialog"]')), 'Reverse Tab stays inside modal');
    await page.keyboard.press('Tab');
    check(await page.evaluate(() => document.activeElement.textContent.includes('跳過')), 'Forward Tab wraps to exit');
    const cdp = await page.createCDPSession();
    let dropped = false;
    await cdp.send('Fetch.enable', { patterns: [{ urlPattern: '*/decision', requestStage: 'Response' }] });
    cdp.on('Fetch.requestPaused', async (e) => { if (!dropped && e.responseStatusCode === 200) {
        dropped = true;
        await cdp.send('Fetch.failRequest', { requestId: e.requestId, errorReason: 'ConnectionReset' });
    }
    else
        await cdp.send('Fetch.continueRequest', { requestId: e.requestId }); });
    await click('確認並執行');
    await status('active');
    await page.waitForFunction(() => document.body.textContent.includes('提交結果尚未確認'));
    check(dropped, 'Lost response after backend acceptance');
    await locked('selected_action', '#reason', 'synthetic retry evidence', 'continue', 'puzzle-pending');
    await sleep(1000);
    await page.reload({ waitUntil: 'networkidle0' });
    await cdp.send('Fetch.disable');
    check(payloads.length === 2, `Refresh replays pending decision once (${payloads.length} requests)`);
    assert.equal(payloads[0], payloads[1]);
    check(true, 'Retry body byte-for-byte identical including key and deliberation_ms');
    check(!('preferred_action_ids' in JSON.parse(payloads[0])), 'Unasked preference field omitted');
    console.log('Waiting for real 45-second followup threshold');
    await status('completed', 50000);
    t = await current();
    check(t.public_state.followup_timeout, 'Post-decision timeout enters followup');
    check(t.active_play_ms === t.public_state.post_decision_started_ms + 45000, 'Reload preserves followup deadline');
    const detail = await api(`/api/operator/sessions/${created.session.session_id}`);
    check(detail.events.filter(e => e.trial_id === id && e.event_type === 'decision_opened').length === 1, 'Only one primary decision opened');
    check(detail.events.filter(e => e.trial_id === id && e.event_type === 'decision_committed').length === 1, 'Retry creates one decision');
    await next('前進下一題');
    for (let index = 1; index < 6; index++) {
        t = await current();
        check(t.active_play_ms < 1500, `${t.item_id}: timer reset`);
        check(await page.evaluate(() => [...document.querySelectorAll('span')].some(el => /^[01] 秒$/.test(el.textContent))), `${t.item_id}: visible timer reset`);
        await click('我想看看協助選項');
        await page.waitForSelector('[role="dialog"]');
        t = await current();
        await blank(t, 'selected_action');
        if (index === 1) {
            await page.focus('[role="dialog"] button');
            await page.keyboard.press('Enter');
            await status('skipped');
            check(true, 'Keyboard skip from modal without invented answer');
        }
        else {
            await fill('selected_action', index === 2 ? 'hint' : index === 3 ? 'continue' : 'solution');
            if (index === 3) {
                await externalVersionChange();
                await click('確認並執行');
                await page.waitForFunction(() => document.body.textContent.includes('重新確認'));
                check(await page.$eval('#reason', el => !el.matches(':disabled')), 'Puzzle definitive rejection unlocks edits');
                check(await page.evaluate(id => !localStorage.getItem(`preference_lab_pending_${id}`), id), 'Puzzle rejected request cleared');
                await page.click('input[name="selected_action"][value="solution"]');
                await page.type('#reason', 'reconfirmed new puzzle answer');
            }
            await click('確認並執行');
            if (index === 2) {
                await status('active');
                await page.waitForFunction(() => document.body.textContent.includes('方向引導提示'));
                check(true, 'Authoritative revealed_hint shown');
                await click('跳過此題');
                await status('skipped');
            }
            else {
                await status('completed');
                if (index === 3) {
                    const verified = await api(`/api/operator/sessions/${created.session.session_id}`);
                    check(verified.trials.find(trial => trial.trial_id === id).decision.selected_action_id === 'solution', 'Puzzle reconfirmation commits new selection');
                }
            }
        }
        await next('前進下一題');
    }
    t = await current();
    check(t.public_state.tutorial_type === 'demonstration', 'BRET demonstration tutorial');
    await shot('bret-tutorial');
    while ((await current()).status !== 'completed') {
        await click('執行此展示步驟');
        await sleep(250);
    }
    await next('進入下一題');
    t = await current();
    check(t.public_state.tutorial_type === 'comprehension', 'BRET comprehension tutorial');
    const fixture = JSON.parse(fs.readFileSync('../instruments/bret_discrete/v001/tutorial_02.json', 'utf8'));
    for (const q of fixture.private_data.comprehension_check.questions)
        await page.click(`input[name="${q.question_id}"][value="${q.correct_answer}"]`);
    await click('送出理解回答');
    await status('completed');
    await shot('bret-comprehension');
    await next('前進先導題目');
    for (let index = 0; index < 4; index++) {
        await status('decision_open');
        await page.waitForSelector('input[name="selected_bret_action"]');
        t = await current();
        await blank(t, 'selected_bret_action');
        await fill('selected_bret_action', t.display_order[index]);
        if (index === 0) {
            await page.type('textarea', 'synthetic BRET draft');
            await page.reload({ waitUntil: 'networkidle0' });
            check(await page.$eval('textarea', i => i.value === 'synthetic BRET draft'), 'BRET draft survives reload');
            assert.deepEqual(await page.$$eval('input[name=selected_bret_action]', els => els.map(el => el.value)), t.display_order);
            check(true, 'BRET order survives reload');
            await page.$eval('input[name=selected_bret_action]', el => el.closest('form').scrollIntoView({ block: 'start' }));
            await shot('bret-pilot');
        }
        if (index === 1) {
            await externalVersionChange();
            await click('確認並執行');
            await page.waitForFunction(() => document.body.textContent.includes('版本衝突'));
            check(await page.$eval('textarea', el => !el.matches(':disabled')), 'BRET definitive rejection unlocks edits');
            const alternative = t.display_order[2];
            await page.click(`input[name="selected_bret_action"][value="${alternative}"]`);
            await page.type('textarea', 'reconfirmed new BRET answer');
        }
        let bretCdp, bretDropped = false;
        const payloadOffset = payloads.length;
        if (index === 0) {
            bretCdp = await page.createCDPSession();
            await bretCdp.send('Fetch.enable', { patterns: [{ urlPattern: '*/decision', requestStage: 'Response' }] });
            bretCdp.on('Fetch.requestPaused', async e => {
                if (!bretDropped && e.responseStatusCode === 200) {
                    bretDropped = true;
                    await bretCdp.send('Fetch.failRequest', { requestId: e.requestId, errorReason: 'ConnectionReset' });
                } else await bretCdp.send('Fetch.continueRequest', { requestId: e.requestId });
            });
        }
        await click('確認並執行');
        await status('completed');
        if (index === 0) {
            await locked('selected_bret_action', 'textarea', 'synthetic BRET draft', t.display_order[0], 'bret-pending');
            await click('重試原提交');
            await bretCdp.send('Fetch.disable');
            await page.waitForFunction(() => document.body.textContent.includes('本輪結算'));
            check(bretDropped && payloads.length === payloadOffset + 2, 'BRET lost response retried exactly once');
            assert.equal(payloads[payloadOffset], payloads[payloadOffset + 1]);
            check(true, 'BRET retry body byte-identical');
        }
        await page.waitForFunction(() => document.body.textContent.includes('本輪結算'));
        if (index === 1) {
            const verified = await api(`/api/operator/sessions/${created.session.session_id}`);
            check(verified.trials.find(trial => trial.trial_id === id).decision.selected_action_id === t.display_order[2], 'BRET reconfirmation commits new selection');
        }
        if (index === 0) {
            await page.evaluate(() => [...document.querySelectorAll('h3')].find(el => /命中炸彈/.test(el.textContent))?.scrollIntoView({ block: 'center' }));
            await shot('bret-result');
        }
        if (index < 3)
            await next('前進下一回合');
        else
            await click('完成全部試驗');
    }
    await page.waitForFunction(() => document.body.textContent.includes('您已完成本次試驗'));
    check((await api('/api/sessions/join', { session_code: code })).session_completed, 'All 12 trials complete');
    check(!errors.length, `No browser runtime errors: ${errors.join(', ')}`);
    await page.goto(APP + '?view=operator', { waitUntil: 'networkidle0' });
    await page.locator(`xpath///tr[contains(., ${JSON.stringify(code)})]//button[contains(., '檢視')]`).click();
    await page.waitForFunction(() => document.body.textContent.includes('試驗題目清單與完成狀態 (12)'));
    check(await page.evaluate(() => document.body.textContent.includes('decision_committed')), 'Operator detail displays completed trials and event log');
    await page.$eval('button', () => { const heading = [...document.querySelectorAll('h4')].find(el => el.textContent.includes('試驗題目清單')); heading.closest('div.bg-white').scrollIntoView(); window.scrollBy(0, -75); });
    await shot('operator-detail');
    const downloads = path.join(out, `downloads-${Date.now()}`);
    fs.mkdirSync(downloads);
    const downloadCdp = await page.createCDPSession();
    await downloadCdp.send('Browser.setDownloadBehavior', { behavior: 'allow', downloadPath: downloads });
    const exportedResponse = page.waitForResponse(r => r.url().endsWith('/export'));
    await click('匯出完整 Session ZIP');
    const exportResponse = await exportedResponse;
    check(exportResponse.ok(), 'Operator ZIP click authenticates successfully');
    for (let attempt = 0; attempt < 100 && !fs.readdirSync(downloads).some(name => name.endsWith('.zip')); attempt++) await sleep(100);
    const downloaded = fs.readdirSync(downloads).find(name => name.endsWith('.zip'));
    check(downloaded, 'Operator browser ZIP download completes');
    const provenance = JSON.parse(execFileSync(path.resolve('../backend/.venv/Scripts/python.exe'), ['-c', `import sqlite3,zipfile,json,sys
with sqlite3.connect(sys.argv[1]) as conn:
 rows=conn.execute("SELECT d.trial_id,d.source FROM decisions d JOIN trials t ON t.trial_id=d.trial_id WHERE t.session_id=?",(sys.argv[3],)).fetchall()
with zipfile.ZipFile(sys.argv[2]) as z:
 decisions=json.loads(z.read('decisions.json'))
assert rows and all(source=='synthetic_mock' for _,source in rows)
assert sorted(rows)==sorted((d['trial_id'],d['source']) for d in decisions)
print(json.dumps({'decisions':len(rows),'source':'synthetic_mock'}))`, database, path.join(downloads, downloaded), created.session.session_id], { encoding: 'utf8' }));
    check(provenance.decisions === 9, 'SQLite and downloaded ZIP have matching synthetic_mock decisions');
    fs.writeFileSync(path.join(out, 'report.json'), JSON.stringify({ viewport: '1280x720', synthetic: true, checks, errors }, null, 2));
    console.log(`Completed ${checks.length} assertions: ${out}`);
}
catch (err) {
    console.error(err);
    await shot('failure').catch(() => { });
    fs.writeFileSync(path.join(out, 'failure.txt'), err.stack);
    throw err;
}
finally {
    await browser.close();
    backend.kill();
    frontend.kill();
}
