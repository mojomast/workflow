// Boot the REAL Orbit routes from an orbitdesktop checkout on a loopback, non-default port:
//   /api/local-workers   (server/local-workers-route.mjs: worker dispatch + capability-gated artifacts)
//   /api/acdd-evidence   (server/acdd-evidence-route.mjs, when present: read-only evidence view)
// It never touches a live Orbit or launcher: the launcher URL and token file come from the harness
// (a loopback hyvv started by hyvv_host.py, or an explicitly opted-in live host).
// env: ORBIT_SRC, ORBIT_RUNTIME, LAUNCHER_URL, LAUNCHER_TOKEN_FILE, BB_STATE (bundlebees state dir), ARTIFACT_MAX
// Prints one JSON line {"url": ..., "evidence_route": bool}.
import http from 'node:http';
import path from 'node:path';
import { existsSync, readFileSync, mkdirSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import { timingSafeEqual } from 'node:crypto';

const src = process.env.ORBIT_SRC;
const runtimeRoot = process.env.ORBIT_RUNTIME;
mkdirSync(runtimeRoot, { recursive: true });
const imp = (rel) => import(pathToFileURL(path.join(src, rel)).href);
const { createLocalWorkersRoute } = await imp('server/local-workers-route.mjs');
const lw = createLocalWorkersRoute({ runtimeRoot, port: 1, env: {
  ORBIT_LOCAL_WORKERS_NODE: 'acceptance',
  ORBIT_LOCAL_WORKERS_URL: process.env.LAUNCHER_URL,
  ORBIT_LOCAL_WORKERS_TOKEN_FILE: process.env.LAUNCHER_TOKEN_FILE,
  ORBIT_LOCAL_WORKERS_POLL_MS: '200', ORBIT_LOCAL_WORKERS_MAX: '4',
  ...(process.env.ARTIFACT_MAX ? { ORBIT_WORKER_ARTIFACT_MAX_BYTES: process.env.ARTIFACT_MAX } : {}),
} });
let evidence = null;
if (existsSync(path.join(src, 'server', 'acdd-evidence-route.mjs')) && process.env.BB_STATE) {
  const { createAcddEvidenceRoute } = await imp('server/acdd-evidence-route.mjs');
  const authorize = (req) => {
    let key; try { key = Buffer.from(readFileSync(path.join(runtimeRoot, 'collab-board.key'), 'utf8').trim()); } catch { return false; }
    const got = Buffer.from(String(req.headers.authorization || '').replace(/^Bearer /, ''));
    return got.length === key.length && timingSafeEqual(got, key);
  };
  evidence = createAcddEvidenceRoute({ stateDir: process.env.BB_STATE, authorize });
}
const server = http.createServer((req, res) => {
  const url = new URL(req.url, 'http://127.0.0.1');
  if (url.pathname === '/api/local-workers') return lw.handle(req, res);
  if (evidence && url.pathname === '/api/acdd-evidence') return evidence.handle(req, res, url);
  res.writeHead(404, { 'Content-Type': 'application/json' }); res.end('{"error":"not found"}');
});
await new Promise((r) => server.listen(0, '127.0.0.1', r));
process.stdout.write(JSON.stringify({ url: `http://127.0.0.1:${server.address().port}`, evidence_route: !!evidence }) + '\n');
