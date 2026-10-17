'use strict';
// Development verification tool only; Playwright and Chromium are supplied by the environment.
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const path = require('node:path');
(async () => {
  const origin=process.argv[2];
  assert.match(origin,/^http:\/\/127\.0\.0\.1:\d+$/);
  const browser=await chromium.launch({executablePath:'/usr/bin/chromium',headless:true,args:['--no-sandbox','--disable-background-networking','--disable-component-update','--disable-sync','--no-first-run']});
  const context=await browser.newContext({viewport:{width:1280,height:960},reducedMotion:'reduce'});
  const page=await context.newPage();page.setDefaultTimeout(10000);
  const external=[],errors=[];
  await context.route('**/*',route=>{
    if(!route.request().url().startsWith(origin+'/')) {external.push('external request');return route.abort();}
    return route.continue();
  });
  page.on('pageerror',error=>errors.push(error.message));
  try {
    await page.goto(origin+'/command-center');
    await page.getByRole('status').filter({hasText:'Empty:'}).waitFor();
    assert.equal(await page.locator('h1').count(),1);
    assert.deepEqual(await page.locator('.stages h3').allTextContents(),['INFORMATION','INTELLIGENCE','DECISION','ASSIGNMENT','EXECUTION','MEASUREMENT']);
    for(const stage of ['information','intelligence','decision','assignment','execution','measurement']) {
      await page.locator('#'+stage).scrollIntoViewIfNeeded();assert(await page.locator('#'+stage).isVisible());
    }
    const cookies=await context.cookies();assert.equal(cookies.length,1);
    assert(cookies[0].httpOnly);assert.equal(cookies[0].sameSite,'Strict');assert.equal(cookies[0].path,'/command-center');
    assert.equal(await page.evaluate(()=>localStorage.length+sessionStorage.length),0);
    // Native keyboard flow: select -> prepare -> checkbox -> confirm.
    await page.locator('#action').selectOption('syn-ui-action-1');
    await page.locator('#prepare').focus();await page.keyboard.press('Enter');
    await page.locator('#confirmation[open]').waitFor();
    assert(await page.locator('#confirm').isDisabled());
    assert.equal(await page.evaluate(()=>document.activeElement.id),'understood');
    await page.keyboard.press('Space');await page.keyboard.press('Tab');
    assert.equal(await page.evaluate(()=>document.activeElement.id),'confirm');
    await page.keyboard.press('Enter');
    await page.getByRole('status').filter({hasText:'Successful synthetic action.'}).waitFor();
    assert.equal(await page.evaluate(()=>document.activeElement.id),'status');
    await page.locator('#refresh').click();
    await page.getByRole('status').filter({hasText:'Authorized views loaded.'}).waitFor();
    assert(await page.getByText('syn-entry-class',{exact:true}).first().isVisible());
    // Refresh and history navigation perform no mutation.
    await page.reload();await page.getByRole('status').filter({hasText:'Authorized views loaded.'}).waitFor();
    assert(await page.locator('#action option[value="syn-ui-action-2"]').isDisabled());
    assert(!(await page.locator('#confirmation').isVisible()));
    // Malicious provider-like output must be text, never executable markup.
    await page.route('**/command-center/api/overview',async route=>{
      const response=await route.fetch();const value=await response.json();
      value.queues[0].items[0].original_classification='<img src=x onerror="window.injected=true">';
      await route.fulfill({response,json:value});
    });
    await page.locator('#refresh').click();await page.getByRole('status').filter({hasText:'Authorized views loaded.'}).waitFor();
    assert.equal(await page.locator('#records img').count(),0);
    assert.equal(await page.evaluate(()=>window.injected),undefined);
    // The stylesheet and native controls remain usable at narrow widths and 200% layout zoom.
    await page.setViewportSize({width:360,height:900});
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth), 'layout overflow');
    await page.setViewportSize({width:1280,height:960});
    await page.evaluate(()=>document.body.style.zoom='2');
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth), 'layout overflow');
    await page.evaluate(()=>document.body.style.zoom='1');
    assert.equal(await page.evaluate(()=>getComputedStyle(document.documentElement).scrollBehavior),'auto');
    // Automated text contrast on visible direct-text elements, following opaque ancestors.
    const contrastFailures=await page.evaluate(()=>{
      function rgb(s){return s.match(/[\d.]+/g)?.map(Number)||[0,0,0,0];}
      function luminance(c){return c.slice(0,3).map(x=>{x/=255;return x<=0.04045?x/12.92:((x+0.055)/1.055)**2.4;}).reduce((v,x,i)=>v+x*[.2126,.7152,.0722][i],0);}
      const failures=[];
      for(const element of document.body.querySelectorAll('*')) {
        if(!element.checkVisibility()||!Array.from(element.childNodes).some(n=>n.nodeType===3&&n.textContent.trim())||element.disabled)continue;
        const style=getComputedStyle(element);if(Number(style.opacity)<1)continue;
        const fg=rgb(style.color);let bg=[255,255,255],parent=element;
        while(parent){const candidate=rgb(getComputedStyle(parent).backgroundColor);if(candidate.length===3||candidate[3]===1){bg=candidate;break;}parent=parent.parentElement;}
        const a=luminance(fg),b=luminance(bg),ratio=(Math.max(a,b)+.05)/(Math.min(a,b)+.05);
        const large=parseFloat(style.fontSize)>=24||(parseFloat(style.fontSize)>=18.66&&parseInt(style.fontWeight)>=700);
        if(ratio<(large?3:4.5))failures.push(element.tagName+': '+element.textContent.trim().slice(0,35)+' ('+ratio.toFixed(2)+')');
      }
      return failures;
    });
    assert.deepEqual(contrastFailures,[]);
    assert.deepEqual(external,[]);assert.deepEqual(errors,[]);
    if(process.env.MC_UI_SCREENSHOT_DIR) await page.screenshot({path:path.join(process.env.MC_UI_SCREENSHOT_DIR,'command-center.png'),fullPage:true});
    console.log('BROWSER PASS: Chromium; six stages; keyboard confirmation; empty/loaded/blocked states; refresh safety; escaping; HttpOnly strict cookie; no browser storage; no external requests; narrow/200% layout; visible text contrast; reduced motion.');
  } catch(error) { console.error('Browser status:',await page.locator('#status').textContent());console.error('Script errors:',errors);console.error('Viewport',await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,zoom:document.body.style.zoom})));throw error; } finally {await context.close();await browser.close();}
})().catch(error=>{console.error(error.message);process.exitCode=1;});
