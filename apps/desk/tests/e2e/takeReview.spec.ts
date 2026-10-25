import { test as base, expect, _electron } from '@playwright/test';
import { mkdtempSync, writeFileSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';
import { build } from 'esbuild';
import { createServer, type Server } from 'node:http';

declare global {
  interface Window {
    showReview: (x: unknown, lang?: string) => void;
    answer: {picks: Record<string,string>; reviews: Record<string,unknown>};
  }
}
const test = base.extend({
  // Playwright requires destructuring the fixture argument.
  // eslint-disable-next-line no-empty-pattern
  page: async ({}, providePage) => {
    const dir = mkdtempSync(path.join(tmpdir(), 'take-review-ui-'));
    const main = path.join(dir, 'main.cjs');
    writeFileSync(main, `const {app,BrowserWindow}=require('electron');app.whenReady().then(()=>{const w=new BrowserWindow({show:true,width:1200,height:900,webPreferences:{backgroundThrottling:false,contextIsolation:true,nodeIntegration:false}});w.loadURL(${JSON.stringify(url)});});`);
    const electron = await _electron.launch({args:[main, '--user-data-dir='+path.join(dir,'profile')]});
    try { await providePage(await electron.firstWindow()); }
    finally { await electron.close(); rmSync(dir,{recursive:true,force:true}); }
  }
});

// The shipped component, with only the desktop bridge and transport replaced by test fixtures.
let server: Server;
let url: string;
test.beforeAll(async () => {
  const mediaDir=mkdtempSync(path.join(tmpdir(),'take-review-media-'));
  let video: Buffer;
  try {
    const file=path.join(mediaDir,'take.mp4');
    execFileSync('ffmpeg',['-v','error','-f','lavfi','-i','color=c=teal:s=320x180:r=24:d=2','-f','lavfi','-i','sine=frequency=440:duration=2','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest',file]);
    video=readFileSync(file);
  } finally {rmSync(mediaDir,{recursive:true,force:true});}
  const bundle = await build({ stdin: { contents: `
    import React from 'react';
    import {createRoot} from 'react-dom/client';
    import {TakeReview} from './src/renderer/src/v4/TakeReview';
    import {setLang} from './src/renderer/src/i18n';
    import './src/renderer/src/theme/global.css';
    import './src/renderer/src/theme/v02.css';
    import './src/renderer/src/theme/app.css';
    import {applyTheme} from './src/renderer/src/theme/tokens';
    applyTheme('notebook-light');
    window.desk={mediaUrl:p=>'/media/'+p};
    const root=createRoot(document.getElementById('root'));
    window.showReview=(x,lang='en')=>{setLang(lang);root.render(<TakeReview key={JSON.stringify(x)+lang} x={x} onDone={a=>window.answer=a} onSkip={()=>{}}/>)};
  `, resolveDir: path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..'), loader: 'tsx' }, bundle: true, write: false, outdir: 'unused', jsx: 'automatic' });
  server = createServer((req,res) => {
    const ext=req.url==='/bundle.js'?'js':req.url==='/style.css'?'css':null;
    if(ext) {res.setHeader('Content-Type',ext==='js'?'text/javascript':'text/css');res.end(bundle.outputFiles.find(f=>f.path.endsWith('.'+ext))?.text??'');}
    else if(req.url?.startsWith('/media/')) {res.setHeader('Content-Type','video/mp4');res.setHeader('Content-Length',video.length);res.end(video);}
    else res.end('<html><head><link rel="stylesheet" href="/style.css"></head><body><div class="v4 page" style="height:100%;overflow:auto"><div id="root"></div></div><script src="/bundle.js"></script></body></html>');
  });
  await new Promise<void>(resolve=>server.listen(0,'127.0.0.1',resolve));
  url=`http://127.0.0.1:${(server.address() as {port:number}).port}`;
});
test.afterAll(async()=>{if (!server) return; await new Promise<void>(resolve=>server.close(()=>resolve()));});
const card={hard:{identity_drift:false,lipsync_or_line:null},soft:{sound_mismatch:null},scores:{A:4,B:4,C:4}};
const candidate=(file:string,stale=false)=>({file,revision:'rev-'+file,stale,review:'review',scorecard:card});
const item={kind:'take-selection',take_units:[{unit:'opening',takes:[candidate('one.mp4'),candidate('two.mp4')]},{unit:'ending',takes:[{...candidate('end.mp4'),scorecard:{...card,hard:{identity_drift:false,lipsync_or_line:false},soft:{sound_mismatch:false}}}]}]};

test('all shots submit selected takes and revision-bound human checks',async({page})=>{
  await page.goto(url);
  await page.evaluate(x=>window.showReview(x),item);
  await expect(page.getByTestId('take-unit')).toHaveCount(2);
  await expect(page.getByTestId('take-continue')).toBeDisabled();
  const first=page.getByTestId('take-unit').first();
  await first.getByRole('radio').nth(1).check();
  await expect(first.locator('video')).toHaveAttribute('src','/media/two.mp4?v=rev-two.mp4');
  await expect(first.locator('video')).toHaveAttribute('controls','');
  // Muted playback isolates decoding from unavailable host audio output on locked/CI machines.
  await first.locator('video').evaluate(async (v:HTMLVideoElement)=>{v.muted=true;await v.play();});
  await expect.poll(()=>first.locator('video').evaluate((v:HTMLVideoElement)=>v.currentTime)).toBeGreaterThan(0.1);
  await first.locator('video').evaluate((v:HTMLVideoElement)=>v.pause());
  await page.screenshot({path:test.info().outputPath('review-en.png'),fullPage:true});
  await first.getByLabel('Dialogue and lip synchronization').selectOption('false');
  await first.getByLabel('Sound fits the scene').selectOption('false');
  await expect(first.getByRole('radio').nth(1)).toHaveAccessibleName('Take 2 · Review passed');
  await expect(page.getByTestId('take-continue')).toBeEnabled();
  await page.getByTestId('take-continue').click();
  const answer=await page.evaluate(()=>window.answer);
  expect(answer.picks).toEqual({opening:'two.mp4',ending:'end.mp4'});
  expect(answer.reviews.opening).toEqual({revision:'rev-two.mp4',hard:{identity_drift:false,lipsync_or_line:false},soft:{sound_mismatch:false},scores:{A:4,B:4,C:4}});
  expect(answer.reviews.ending).toBeUndefined();
});
test('changed evidence blocks approval in every supported language',async({page})=>{
  await page.goto(url);
  for(const lang of ['en','zh-CN','fr']) {
    await page.evaluate(({x,lang})=>window.showReview(x,lang),{x:{...item,take_units:[{unit:'opening',takes:[candidate('changed.mp4',true)]}]},lang});
    await expect(page.getByRole('alert')).toBeVisible();
    await expect(page.getByTestId('take-continue')).toBeDisabled();
    for(const select of await page.locator('select').all()) await expect(select).toBeDisabled();
    await expect(page.locator('body')).not.toContainText('⟦');
  }
  await page.screenshot({path:test.info().outputPath('review-fr.png'),fullPage:true});
});
