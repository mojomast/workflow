// Private fixture host: real Orbit shell module, read proxy and opaque renderer.
// Local dependency paths and freshly generated credentials arrive on stdin only.
import assert from 'node:assert/strict';
import {randomBytes} from 'node:crypto';
import {readFile} from 'node:fs/promises';
import http from 'node:http';
import {createRequire} from 'node:module';
import {join} from 'node:path';
import {createInterface} from 'node:readline';
import {pathToFileURL} from 'node:url';

const lines = createInterface({input:process.stdin})[Symbol.asyncIterator]();
const next = async () => JSON.parse((await lines.next()).value);
const ack = value => process.stdout.write(JSON.stringify(value)+'\n');
const cfg = await next();
const require = createRequire(import.meta.url);
const esbuild = require(join(cfg.modules,'esbuild'));
const {chromium} = await import(pathToFileURL(join(cfg.modules,'playwright-core/index.mjs')));
const {createRailsProxy} = await import(pathToFileURL(join(cfg.orbit,'server/rails-proxy.mjs')));
const bundle = await esbuild.build({entryPoints:[join(cfg.orbit,'src/rails-shell.ts')],bundle:true,
  format:'esm',platform:'browser',write:false,logLevel:'silent'});
esbuild.stop();
const owner = randomBytes(32).toString('hex');
const files = new Map([['/', ['text/html',`<!doctype html><body><script type="module">
  import {openRailsShell} from '/shell.js';
  window.selectBench = (owner,id) => openRailsShell(()=>owner,{kind:'job',id});
</script></body>`]], ['/shell.js',['text/javascript',bundle.outputFiles[0].contents]]]);
for (const name of ['index.html','app.js','rails.js','styles.css','inspector.js','feedback.js']) {
  files.set('/rails-pane/'+name,[name.endsWith('.html')?'text/html':name.endsWith('.css')?'text/css':'text/javascript',
    await readFile(join(cfg.orbit,'apps/rizzstack-rails',name))]);
}
let proxy, stream, connects=0, lastHeader, cut=false;
const host = http.createServer((req,res) => {
  if (req.url.startsWith('/api/rizzstack/rails/')) {
    if (req.url.startsWith('/api/rizzstack/rails/stream?')) {
      if (cut) { res.destroy(); return; }
      stream=res; connects++; lastHeader=req.headers['last-event-id'];
    }
    void proxy(req,res); return;
  }
  const file=files.get(req.url);
  if (!file || req.method!=='GET') {res.writeHead(404).end();return;}
  res.writeHead(200,{'Content-Type':file[0],'Access-Control-Allow-Origin':'*','Cache-Control':'no-store'}).end(file[1]);
});
await new Promise(resolve=>host.listen(0,'127.0.0.1',resolve));
const port = host.address().port, origin=`http://127.0.0.1:${port}`;
proxy=createRailsProxy({token:owner,port,upstreamPort:cfg.port,readTokenFile:cfg.cred});
const browser=await chromium.launch({executablePath:cfg.chrome,headless:true,args:['--disable-dev-shm-usage','--disable-background-networking',
  '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1']});
try {
  const context=await browser.newContext({viewport:{width:1440,height:1200},reducedMotion:'reduce',serviceWorkers:'block'});
  await context.route('**/*',r=>new URL(r.request().url()).origin===origin?r.continue():r.abort());
  const page=await context.newPage();page.setDefaultTimeout(18000);
  const cdp=await browser.newBrowserCDPSession();
  const memory=async()=>{
    const {processInfo}=await cdp.send('SystemInfo.getProcessInfo');let pss=0;
    for(const {id} of processInfo) pss+=Number((await readFile(`/proc/${id}/smaps_rollup`,'utf8')).match(/^Pss:\s+(\d+) kB$/m)[1]);
    return pss;
  };
  const frame=()=>page.frameLocator('iframe');
  const ids=()=>frame().locator('.rail-mark').evaluateAll(es=>es.map(e=>e.dataset.eventId));
  const missing=()=>frame().getByText('offline-worker',{exact:true}).waitFor();
  // Render five assembled 500-row logical pages at once; observe the real cap
  // and equivalent table, independently of append latency on the live selector.
  await page.goto(origin);
  await page.evaluate(view=>{
    const f=document.createElement('iframe'); f.sandbox='allow-scripts'; f.style='width:100%;height:90vh';
    window.addEventListener('message',e=>{
      if(e.source===f.contentWindow&&e.origin==='null'&&e.data?.type==='orbit-rails-renderer-ready')e.ports[0].postMessage({view});
    }); f.src='/rails-pane/index.html';document.body.append(f);
  },cfg.overview);
  await frame().getByText(/2000 visible, 500 hidden/).waitFor();await missing();
  const all=cfg.overview.lanes.flatMap(l=>l.marks.map(m=>m.event_id));
  assert.equal(all.length,2500);assert.equal(new Set(all).size,2500);
  assert.deepEqual(await ids(),all.slice(0,2000));
  assert.deepEqual(await frame().locator('table tr button').allTextContents(),all.slice(0,2000));
  ack({chromium:browser.version(),node:process.version,esbuild:esbuild.version,
    playwright:require(join(cfg.modules,'playwright-core/package.json')).version,viewport_px:[1440,1200],
    input_marks:2500,dom_marks:2000,hidden_marks:500,unique_table_rows:2000});
  await page.goto(origin);await page.waitForFunction(()=>typeof window.selectBench==='function');
  const dialog=page.getByRole('dialog',{name:'Rizzstack Rails'});
  let expected=[],selector,cursor;
  for (;;) {
    const cmd=await next();if(cmd.op==='close')break;
    if(cmd.op==='select') {
      selector='live-'+cmd.window;expected=[cmd.id];cursor=null;
      await page.evaluate(([owner,id])=>{window.selectBench(owner,id);},[owner,selector]);
      await dialog.getByRole('button',{name:'Inspect history'}).click();
      await dialog.getByText(/Connected to updates/).waitFor();await missing();
      assert.deepEqual(await ids(),expected);ack('armed');continue;
    }
    assert.ok(['connected','replay'].includes(cmd.op));
    const replay=cmd.op==='replay',before=connects,previous=cursor;
    if(replay) {
      assert.ok(previous&&stream&&!stream.destroyed);cut=true;stream.destroy();
      await dialog.getByText(/Stream disconnected/).waitFor();
    } else assert.ok(stream&&!stream.destroyed);
    const response=page.waitForResponse(r=>{
      const u=new URL(r.url());return u.pathname==='/api/rizzstack/rails/view'&&u.searchParams.get('id')===selector;
    });
    ack('armed');const id=await next();assert.ok(!expected.includes(id));expected.push(id);cut=false;
    const r=await response;assert.equal(r.status(),200);const body=await r.body();assert.ok(body.length<=131072);
    const view=JSON.parse(body);assert.equal(view.completeness,'partial');assert.deepEqual(view.missing_sources,['offline-worker']);
    assert.deepEqual(view.lanes.flatMap(l=>l.marks.map(m=>m.event_id)),expected);
    cursor=r.headers()['x-rails-stream-cursor'];assert.ok(cursor&&cursor!==previous);
    ack('http');
    const mark=frame().locator(`.rail-mark[data-event-id="${id}"]`);await mark.waitFor();
    // Give the compositor a rendering opportunity, then hit-test the new SVG
    // mark in both frame and host coordinates. No scrollIntoView or auto-click.
    assert.ok(await mark.evaluate(el=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>{
      const b=el.getBoundingClientRect();resolve(b.width>0&&b.height>0&&
        document.elementFromPoint(b.x+b.width/2,b.y+b.height/2)===el);
    })))));
    const box=await mark.boundingBox();assert.ok(box);
    assert.ok(await page.evaluate(({x,y,width,height})=>document.elementFromPoint(x+width/2,y+height/2)?.tagName==='IFRAME',box));
    assert.deepEqual(await ids(),expected);await missing();
    assert.ok(stream&&!stream.destroyed);assert.equal(connects,before+Number(replay));
    if(replay) assert.equal(lastHeader,previous);
    ack({id,count:expected.length,view_bytes:body.length,resumed:replay,chromium_pss_kib:await memory()});
  }
} finally { await browser.close();host.closeAllConnections();host.close();process.stdin.destroy(); }
