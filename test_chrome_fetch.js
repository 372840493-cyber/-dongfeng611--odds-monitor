const playwright = require('C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
(async () => {
  const b = await playwright.chromium.launch({
    headless: true,
    executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
    args: ['--disable-blink-features=AutomationControlled', '--no-first-run'],
  });
  const ctx = await b.newContext({ locale: 'zh-CN' });
  const page = await ctx.newPage();
  const url = 'https://vip.titan007.com/OverDown_n.aspx?id=3095429&l=0';
  const resp = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 }).catch(e => null);
  await page.waitForTimeout(2500);
  const html = await page.content();
  console.log('STATUS', resp ? resp.status() : 'ERR', 'LEN', html.length, 'TITLE', await page.title());
  console.log('HAS_TABLE', /pl_table_data|大小指数|大球/.test(html));
  await b.close();
})();
