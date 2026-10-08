const assert = require('node:assert/strict');
const fs = require('node:fs');
(async () => {
 const src = fs.readFileSync('src/lib/watchBatch.js', 'utf8');
 const { watchBatch } = await import('data:text/javascript;base64,' + Buffer.from(src).toString('base64'));
 const flush = () => new Promise(r => setImmediate(r));
 let queued, calls = 0, reads = 0, completed = 0, events = [];
 const stop = watchBatch({
  readJob: async () => { calls++; if(calls===2) throw new Error('temporary network error'); return {processed:calls===1?1:2,status:calls===1?'processing':'done'}; },
  readPhotos: async () => { reads++; if(reads===2) throw new Error('final refresh failed'); return [{current_path:reads===1?'first-edit.jpg':'last-edit.jpg'}]; },
  onJob: j => events.push(j.status), onPhotos: p => events.push(p[0].current_path),
  onComplete: () => {completed++; events.push('complete');}, onError: e => {throw e;},
  schedule: fn => {queued=fn; return 1;}, cancel: () => {},
 });
 await flush(); assert(events.includes('first-edit.jpg')); assert.equal(completed,0);
 await queued(); assert.equal(completed,0); // Network failure must not stop polling.
 await queued(); assert.equal(completed,0); // Completion waits for fresh final images.
 await queued(); assert.equal(completed,1); assert.equal(events.at(-2),'last-edit.jpg');
 stop();
 let resolve, published=false, scheduled=false;
 const cancel = watchBatch({readJob:()=>new Promise(r=>resolve=r),readPhotos:async()=>[],onJob:()=>published=true,onPhotos:()=>published=true,onComplete:()=>published=true,onError:()=>published=true,schedule:()=>scheduled=true,cancel:()=>{}});
 cancel(); resolve({processed:0,status:'done'}); await flush(); assert.equal(published,false); assert.equal(scheduled,false);
 let interrupted=false;
 watchBatch({readJob:async()=>({processed:19,status:'interrupted'}),readPhotos:async()=>[],onJob:()=>{},onPhotos:()=>{},onComplete:()=>interrupted=true,onError:e=>{throw e;},schedule:()=>{throw new Error('Interrupted jobs must stop polling');},cancel:()=>{}});
 await flush(); assert.equal(interrupted,true);
 console.log('Batch refresh regression checks passed: progress, transient errors, final refresh retry, cancellation.');
})().catch(e=>{console.error(e);process.exitCode=1;});
