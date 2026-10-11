import puppeteer from 'puppeteer-core';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
const APP = process.env.APP_URL || 'http://127.0.0.1:18731', API = process.env.API_URL || 'http://127.0.0.1:18732';
const out = path.resolve('../runs/part-c/browser');
fs.mkdirSync(out, { recursive: true });
const checks = [], errors = [], payloads = [];
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
// Keep local servers and Chrome in the same host execution context.
const backend = spawn(path.resolve('../backend/.venv/Scripts/python.exe'), ['-m', 'uvicorn', 'preference_lab.api.app:app', '--host', '127.0.0.1', '--port', new URL(API).port], {
    cwd: path.resolve('../backend'), windowsHide: true,
    env: { ...process.env, PREFERENCE_LAB_DB: path.join(out, `synthetic-${Date.now()}.sqlite3`) }, stdio: ['ignore', 'ignore', 'pipe'],
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
async function next(text) { await click(text); await sleep(350); id = (await api('/api/sessions/join', { session_code: code })).current_trial_id; }
try {
    await page.goto(APP + '?view=operator', { waitUntil: 'networkidle0' });
    check(await page.$('input[placeholder="例如: P_001"]'), '?view=operator entry');
    await shot('operator');
    const created = await api('/api/operator/sessions', { participant_id: 'llm_synthetic_part_c_e2e' });
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
    await page.waitForFunction(() => document.body.textContent.includes('Failed to fetch'));
    check(dropped, 'Lost response after backend acceptance');
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
            await fill('selected_action', index === 2 ? 'hint' : 'solution');
            await click('確認並執行');
            if (index === 2) {
                await status('active');
                await page.waitForFunction(() => document.body.textContent.includes('方向引導提示'));
                check(true, 'Authoritative revealed_hint shown');
                await click('跳過此題');
                await status('skipped');
            }
            else
                await status('completed');
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
        await click('確認並執行');
        await status('completed');
        await page.waitForFunction(() => document.body.textContent.includes('本輪結算'));
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
    await shot('operator');
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
