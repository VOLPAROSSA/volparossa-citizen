import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
import { chromium, firefox, webkit } from 'playwright';
import AxeBuilder from '@axe-core/playwright';

const url = process.env.QA_URL || 'http://127.0.0.1:8799/volparossa-citizen/';
const artifacts = new URL('../qa/browser/', import.meta.url).pathname;
await mkdir(artifacts, {recursive:true});
for (const engine of (process.env.QA_ENGINES || 'chromium').split(',')) {
  const options = engine === 'chromium' && process.env.CHROME_PATH ? {executablePath: process.env.CHROME_PATH} : {};
  const browser = await ({chromium, firefox, webkit})[engine].launch(options);
  try {
    for (const width of [1440, 768, 390, 320]) {
      const context = await browser.newContext({viewport:{width,height:900},reducedMotion:'reduce'});
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', e => errors.push(e.message));
      page.on('response', r => {if (r.status() >= 400) errors.push(r.url());});
      assert.equal((await page.goto(url)).status(), 200);
      await page.evaluate(async () => {
        for (const img of document.images) img.loading = 'eager';
        await new Promise(resolve => requestAnimationFrame(resolve));
        await Promise.all(Array.from(document.images, img => img.decode()));
        await document.fonts.ready;
      });
      async function checkLayout(mode) {
        const dimensions = await page.evaluate(() => ({
          page: document.documentElement.scrollWidth,
          root: document.documentElement.clientWidth,
          viewport: window.innerWidth,
          table: document.querySelector('.results table').getBoundingClientRect().right,
        }));
        assert(dimensions.page <= dimensions.viewport + 1 && dimensions.table <= dimensions.root + 1,
          engine + ' ' + width + 'px ' + mode + ': ' + JSON.stringify(dimensions));
      }
      await checkLayout('default');
      if ([1440,390].includes(width)) await page.screenshot({fullPage:true,path:artifacts + engine + '-' + width + '.png'});
      assert.equal(await page.getByRole('heading', {level:1, name:'Follow a town proposal.'}).count(),1);
      const table = page.getByRole('table', {name:'Three simulated outcomes for the same proposal'});
      assert.equal(await table.getByRole('columnheader').count(),3);
      assert.equal(await table.getByRole('row').count(),4);
      assert.deepEqual(await table.getByRole('cell').allTextContents(),
        ['67','34','Indeterminate','68','33','Adopted','33','68','Rejected']);

      await page.keyboard.press('Tab');
      const focus = page.locator(':focus');
      assert.equal(await focus.textContent(), 'Skip to content');
      assert(await focus.evaluate(el => el.matches(':focus-visible') && getComputedStyle(el).outlineStyle !== 'none'));
      await page.keyboard.press('Enter');
      assert.equal(await focus.getAttribute('id'), 'main');
      const mobile = await page.locator('.mobile-nav').isVisible();
      const nav = page.locator(mobile ? '.mobile-nav' : '.desktop-nav');
      if (mobile) await nav.locator('summary').click();
      const toggle = nav.locator('.applications-toggle');
      if (mobile) await toggle.click(); else await nav.locator('.applications-menu').hover();
      assert(await nav.getByRole('link',{name:'Citizen',exact:true}).isVisible());
      await toggle.focus();
      await page.keyboard.press('Escape');
      assert.equal(await toggle.getAttribute('aria-expanded'),'false');
      if (mobile) await page.keyboard.press('Escape');
      await page.getByRole('link',{name:'Follow the proposal'}).click();
      assert.equal(new URL(page.url()).hash,'#proposal');
      await page.getByText('Who can take part?', {exact:true}).focus();
      await page.keyboard.press('Enter');
      assert(await page.getByText('Taking part requires an account', {exact:false}).isVisible());
      await page.getByText('Check the support threshold',{exact:true}).click();
      assert(await page.getByText('Count each supporter once.',{exact:false}).isVisible());
      await page.getByRole('link',{name:'Explore the results'}).click();
      assert.equal(new URL(page.url()).hash,'#results');
      assert([200,304].includes((await page.reload()).status()));
      await page.getByText('Check the decision threshold',{exact:true}).click();
      assert(await page.getByText('Twice the electorate is 202.',{exact:false}).isVisible());
      if (engine === 'chromium' && [320,1440].includes(width)) {
        const audit = await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21a','wcag21aa']).analyze();
        assert.deepEqual(audit.violations.map(v => [v.id, v.nodes.map(n => n.target)]),[]);
      }
      await page.addStyleTag({content:'html{font-size:200%}'});
      await checkLayout('200% text');
      assert.deepEqual(errors,[]);
      await context.close();
    }
    const plain = await browser.newPage({viewport:{width:390,height:844},javaScriptEnabled:false});
    await plain.route('**/*', r => r.request().resourceType()==='image' ? r.abort() : r.continue());
    await plain.goto(url);
    await plain.locator('.mobile-nav summary').click();
    assert(await plain.locator('.mobile-nav').getByRole('link',{name:'Applications',exact:true}).isVisible());
    await plain.locator('.mobile-nav summary').click();
    await plain.getByText('Who can take part?', {exact:true}).click();
    assert(await plain.getByText('Taking part requires an account', {exact:false}).isVisible());
    assert(await plain.getByRole('cell',{name:'Indeterminate'}).isVisible());
    assert(await plain.getByText('Support for the new procedure').isVisible());
    console.log(engine + ': four sizes, 200% type, keyboard, accessible table, anchor reloads and fallbacks passed.');
  } finally {
    await browser.close();
  }
}
