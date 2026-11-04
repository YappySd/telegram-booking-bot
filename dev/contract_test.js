const { chromium } = require('playwright');
const { spawn, execSync } = require('child_process');
(async () => {
  const srv = spawn('python3', ['contract_server.py'], { cwd: __dirname });
  const init = await new Promise(r => srv.stdout.once('data', d => r(String(d).trim())));
  await new Promise(r => setTimeout(r, 500));
  const b = await chromium.launch();
  const mk = async (initData) => {
    const ctx = await b.newContext({ viewport: { width: 430, height: 932 }, locale: 'ru-RU' });
    await ctx.route('**/telegram.org/**', r => r.fulfill({ contentType: 'application/javascript', body:
      `window.Telegram={WebApp:{initData:${JSON.stringify(initData)},initDataUnsafe:{user:{first_name:'Ярослав'}},themeParams:{},ready(){},expand(){},close(){window.__closed=1},showConfirm(m,cb){cb(true)},BackButton:{show(){},hide(){},onClick(){}},HapticFeedback:{impactOccurred(){},notificationOccurred(){}}}};` }));
    const p = await ctx.newPage(); const errs = [];
    p.on('console', m => m.type()==='error' && errs.push(m.text())); p.on('pageerror', e => errs.push('PAGEERROR '+e.message));
    await p.goto('http://127.0.0.1:8765/'); return { p, errs };
  };
  const out = {};
  let { p, errs } = await mk(init);
  await p.waitForSelector('.service'); out.demoPill = await p.isHidden('#demo');
  await p.click('.service[data-id=cut]'); await p.waitForSelector('.slot');
  const first = await p.textContent('.slot >> nth=0'); await p.click('.slot >> nth=0');
  await p.click('#cta-btn'); await p.fill('#phone', '+380501234567'); await p.click('#cta-btn');
  await p.waitForSelector('.check'); out.booked = (await p.textContent('.done')).includes(first);
  await p.click('.tabs button[data-tab=my]'); await p.waitForSelector('.ticket'); out.myCount = await p.locator('.ticket').count();
  // second user takes nothing; same user double-book same slot via API -> slot_taken toast
  await p.click('.ghost'); await p.waitForSelector('.empty'); out.afterCancel = await p.textContent('.empty');
  // slot_taken: book twice by different users
  const ctx2 = await mk(execSync("python3 -c \"import contract_server as c;print(c.init_data(7,'Олег'))\"", { cwd: __dirname }).toString().trim());
  out.errsMain = errs;
  // bad auth
  const bad = await mk('hash=bad&user=%7B%22id%22%3A1%7D&auth_date=1');
  await bad.p.waitForTimeout(800); out.badAuthMsg = (await bad.p.locator('#toast').textContent()) || (await bad.p.textContent('#view')).slice(0,80);
  console.log(JSON.stringify(out, null, 1));
  await b.close(); srv.kill();
})().catch(e => { console.error(e); process.exit(1); });
