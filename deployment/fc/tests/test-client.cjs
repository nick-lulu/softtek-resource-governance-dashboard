const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const root=path.resolve(__dirname,'../../../public');
(async()=>{
 let requests=0,resolveResponse,events=0;
 const context=vm.createContext({window:{},location:{hostname:'lcorp.msofttek.com'},AbortController,
  Event,setTimeout,clearTimeout,document:{dispatchEvent(){events++}},
  fetch:()=>{requests++;return new Promise(resolve=>resolveResponse=resolve)}});
 vm.runInContext(fs.readFileSync(path.join(root,'assets/timesheet-actuals.js'),'utf8'),context);
 const api=context.window.TimesheetActuals;
 assert.equal(requests,0,'Script startup never blocks planning with a request');
 const pending=api.refresh();
 assert.equal(api.person({key:'nick_han'}),null,'Loading is not zero');
 await api.refresh();assert.equal(requests,1,'Concurrent refresh is deduplicated');
 const fixture={schemaVersion:1,period:{startDate:'2026-11-01',endDate:'2027-01-31'},hoursPerMD:8,
  status:'ready',statusBasis:'filled',resources:[{resourceKey:'nick_han',actualHours:32,actualMD:4}]};
 resolveResponse({ok:true,json:async()=>fixture});await pending;
 assert.equal(api.person({key:'nick_han'}).actualMD,4);
 assert.equal(Math.round(api.summary([{key:'nick_han',total:92.56}]).unspent*100)/100,88.56);
 assert.equal(api.person({key:'unknown'}),null);
 assert.match(api.note({key:'unknown'}),/email/);
 assert.equal(events,1);
 assert(!api.valid({...fixture,resources:[...fixture.resources,...fixture.resources]}));
 context.fetch=async()=>{throw Error('offline')};await api.refresh();
 assert.equal(api.state.status,'stale');assert.equal(api.person({key:'nick_han'}).actualMD,4);
 assert.match(api.note({key:'nick_han'}),/stale/);
 const html=fs.readFileSync(path.join(root,'resources/index.html'),'utf8');
 for(const m of html.matchAll(/<script([^>]*)>([\s\S]*?)<\/script>/g)){
  if(m[1].includes('application/json'))JSON.parse(m[2]);else if(m[2].trim())new vm.Script(m[2]);
 }
 console.log('PASS: asynchronous entry, single request, 32h = 4 MD, 88.56 MD unspent, missing and stale states');
})().catch(e=>{console.error(e);process.exitCode=1});
