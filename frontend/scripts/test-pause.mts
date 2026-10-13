import assert from 'node:assert/strict';
import { api } from '../src/api/client.ts';

let posts = 0;
let reads = 0;
let release!: () => void;
const gate = new Promise<void>(resolve => { release = resolve; });
globalThis.fetch = async (_url, options) => {
  if (options?.method === 'POST') {
    posts++;
    await gate;
    return new Response(JSON.stringify({ status: 'paused', state_version: 2 }));
  }
  throw new Error('Unexpected read');
};
const first = api.pauseTrial('duplicate', 100, 1, 'test-token');
const second = api.pauseTrial('duplicate', 100, 1, 'test-token');
release();
await Promise.all([first, second]);
assert.equal(posts, 1, 'blur and visibilitychange must share one pause request');

for (const status of ['paused', 'skipped', 'completed', 'completed_without_decision', 'aborted']) {
  globalThis.fetch = async (_url, options) => {
    if (options?.method === 'POST') {
      return new Response(JSON.stringify({ detail: `Cannot pause trial in status '${status}'` }), { status: 400 });
    }
    reads++;
    return new Response(JSON.stringify({ status, state_version: 5 }));
  };
  const result = await api.pauseTrial(`settled-${status}`, 100, 1, 'test-token');
  assert.equal(result.status, status);
  assert.equal(result.state_version, 5);
}
assert.equal(reads, 5, 'reconcile rejected pauses with server state');
globalThis.fetch = async () => new Response(JSON.stringify({ detail: 'invalid time' }), { status: 400 });
await assert.rejects(api.pauseTrial('invalid', -1, 1, 'test-token'), /invalid time/);
console.log('Pause regression checks passed');
