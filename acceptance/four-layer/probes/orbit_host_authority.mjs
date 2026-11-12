// Repro for S1 (approval adapter returning a string / pending id) and S5 (default deploy perms).
// usage: node orbit_host_authority.mjs <orbit checkout>   (last stdout line: JSON results)
// EXECUTED means the unsafe action ran; refused:<code> means it was blocked.
import fs from 'node:fs'; import os from 'node:os'; import path from 'node:path';
const root = path.resolve(process.argv[2]);
const { createHostApi } = await import(path.join(root, 'server/host-api.mjs'));
const { createHostAudit } = await import(path.join(root, 'server/host-audit.mjs'));
function host(perms) { return { id: 'h1', label: 'h', address: '203.0.113.10', port: 22, user: 'orbit',
  transport: { kind: 'direct' }, auth: { kind: 'orbit-key', keyId: 'k' }, hostKey: { fingerprints: ['SHA256:x'] },
  privilege: { sudo: 'scoped', docker: 'group' }, permissions: perms, status: { state: 'verified' } }; }
async function run(name, approvalResult, perms, agent, argv) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'rz-'));
  const calls = [];
  const map = new Map([['h1', host(perms)]]);
  const api = createHostApi({ sshHosts: { async get(id) { return map.get(id); }, async list() { return [...map.values()]; } },
    audit: createHostAudit({ runtimeDir: dir }), approvals: { async request() { return typeof approvalResult === 'function' ? approvalResult() : approvalResult; } },
    exec: async (h, a) => { calls.push(a); return { code: 0, stdout: '', stderr: '' }; } });
  let outcome;
  try { await api.hosts.run('h1', argv, { agent }); outcome = calls.length ? 'EXECUTED' : 'no-exec'; }
  catch (e) { outcome = `refused:${e.code}`; }
  console.log(`${name}\t${outcome}`);
  return outcome;
}
const destructive = ['rm', '-rf', '/opt/orbit/worker'];
const res = {};
res.s1_string = await run('S1 approval adapter returns pending-id string', 'approval-pending-123', { a: 'admin' }, 'a', destructive);
res.s1_status = await run('S1 approval {status:"approved"} without approved:true', { status: 'approved' }, { a: 'admin' }, 'a', destructive);
res.s1_decision = await run('S1 approval {decision:"allow"} unauthenticated', { decision: 'allow' }, { a: 'admin' }, 'a', destructive);
res.s1_true = await run('S1 approval bare true', true, { a: 'admin' }, 'a', destructive);
res.s1_timeout = await run('S1 approval adapter throws (timeout)', () => { throw new Error('timeout'); }, { a: 'admin' }, 'a', destructive);
res.s1_null = await run('S1 approval adapter returns null', null, { a: 'admin' }, 'a', destructive);
res.s5_setup = await run('S5 agent "setup" with no host permissions runs uptime', null, undefined, 'setup', ['uptime']);
{ const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'rz-')); const map = new Map([['h1', host(undefined)]]); let wrote = false;
  const api = createHostApi({ sshHosts: { async get(id) { return map.get(id); } }, audit: createHostAudit({ runtimeDir: dir }), approvals: { async request() { return null; } },
    exec: async () => { wrote = true; return { code: 0, stdout: '', stderr: '' }; } });
  try { await api.hosts.put('h1', '/opt/orbit/worker/x.yaml', 'a: 1', { agent: 'setup' }); res.s5_setup_put = wrote ? 'EXECUTED' : 'no-exec'; } catch (e) { res.s5_setup_put = `refused:${e.code}`; }
  console.log(`S5 agent "setup" with no host permissions writes /opt/orbit file (deploy-level)\t${res.s5_setup_put}`); }
res.s5_unknown = await run('S5 unknown agent with no host permissions', null, undefined, 'newbie', ['uptime']);
console.log(JSON.stringify(res));
