// Regenerate workflow-map.png from workflow-map.html (needs Playwright + a Chromium).
// CHROMIUM=/path/to/chrome node render.mjs
import { chromium } from 'playwright';
import { fileURLToPath } from 'node:url'; import path from 'node:path';
const here = path.dirname(fileURLToPath(import.meta.url));
const b = await chromium.launch({ executablePath: process.env.CHROMIUM || undefined });
const p = await b.newPage({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 2 });
await p.goto('file://' + path.join(here, 'workflow-map.html'));
await p.waitForSelector('body[data-ready="1"]');
await p.locator('#poster').screenshot({ path: path.join(here, 'workflow-map.png') });
await b.close();
