import { _electron as electron, test, expect } from '@playwright/test';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { coverAction } from '../../src/main/publish/coverFill';

for (const keepOpener of [false, true]) test(`cover dialog confirms without publishing (opener remains: ${keepOpener})`, async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'reelfold-cover-test-'));
  const main = path.join(tmp, 'main.cjs');
  fs.writeFileSync(main, `const {app,BrowserWindow}=require('electron'); app.setPath('userData',${JSON.stringify(path.join(tmp,'profile'))}); app.whenReady().then(()=>{ const w=new BrowserWindow({show:false}); w.loadURL('about:blank'); });`);
  const app = await electron.launch({ args: [main] });
  try {
    const page = await app.firstWindow();
    await page.route('https://creator.xiaohongshu.com/**', route => route.fulfill({contentType:'text/html; charset=utf-8', body:`
      <main><input type="file" accept="video/*" id="video"><button id="open">设置封面</button><button id="publish" onclick="window.published=true">发布</button><button id="other" onclick="window.otherClicked=true">确定</button>
      </main><script>document.querySelector('#open').onclick=()=>{
        if (!${keepOpener}) document.querySelector('#open').remove();
        document.querySelector('main').insertAdjacentHTML('beforeend','<section id="dialog"><h2>设置封面</h2><span id="upload">上传封面</span><button>取消</button><button id="confirm" disabled>确定</button></section>');
        document.querySelector('#upload').onclick=()=>{
          document.querySelector('#dialog').insertAdjacentHTML('beforeend','<input type="file" accept="image/*">');
          document.querySelector('#dialog input').onchange=()=>{window.cover=document.querySelector('#dialog input').files[0].name; document.querySelector('#confirm').disabled=false;};
        };
        document.querySelector('#confirm').onclick=()=>document.querySelector('#dialog').remove();
      };</script>` }));
    await page.goto('https://creator.xiaohongshu.com/publish/publish');
    expect(await page.evaluate(coverAction('open'))).toBe(true);
    expect(await page.evaluate(coverAction('upload'))).toBe(true);
    expect(await page.evaluate(coverAction('confirm'))).toBe(false);
    expect(await page.evaluate(coverAction('closed'))).toBe(false);
    expect(await page.evaluate(`(${coverAction('input')}).closest('#dialog') !== null`)).toBe(true);
    await page.locator('#dialog input').setInputFiles({name:'chosen.png',mimeType:'image/png',buffer:Buffer.from('image')});
    expect(await page.evaluate(coverAction('confirm'))).toBe(true);
    expect(await page.evaluate(coverAction('closed'))).toBe(true);
    expect(await page.evaluate('({cover:window.cover,published:!!window.published,other:!!window.otherClicked})')).toEqual({cover:'chosen.png',published:false,other:false});
  } finally { await app.close(); }
});
