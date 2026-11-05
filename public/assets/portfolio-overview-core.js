(function(root,factory){if(typeof module==='object'&&module.exports)module.exports=factory();else root.PortfolioOverviewCore=factory();})(typeof window==='undefined'?this:window,function(){'use strict';
const DOMAINS=['Corporate','MP&A','Fulfillment','Upstream SCM & MDM','SCM Ops'];
const domain=s=>s==='Supplychain SCM&MDM'?'Upstream SCM & MDM':s;
const name=s=>String(s||'').normalize('NFKC').toLowerCase().replace(/[^a-z0-9\u4e00-\u9fff]/g,'');
function refs(p){return [...new Set([p.id,...(p.references||[])].filter(Boolean).flatMap(s=>{const out=[];for(const m of String(s).matchAll(/\b(CSCOP|CDM)-(\d+(?:\/\d+)*)/gi))for(const n of m[2].split('/'))out.push(m[1].toUpperCase()==='CDM'&& !['3960','3961'].includes(n)?'CDM-'+n:'CSCOP-'+n);return out;}))];}
const names=p=>[p.name,...(p.aliases||[])].filter(Boolean).map(name);
function match(p,plans){const own=plans.filter(x=>domain(x.domain)===domain(p.domain)),ids=refs(p),byId=own.filter(x=>refs(x).some(id=>ids.includes(id))),byName=own.filter(x=>names(x).some(n=>names(p).includes(n)));
 if(ids.length&&byId.length){const exact=byId.filter(x=>names(x).some(n=>names(p).includes(n))),hits=exact.length?exact:byId,covered=new Set(hits.flatMap(refs));if(hits.length===1&&ids.every(id=>covered.has(id)))return {coverage:'planned',basis:exact.length?'Domain + CSCOP + project name':'Domain + unique CSCOP',planKeys:hits.map(x=>x.key)};return {coverage:'review',basis:'Shared or partially matched reference; verify project identity',planKeys:hits.map(x=>x.key)};}
 if(!ids.length)return {coverage:'review',basis:byName.length?'Project name found; CSCOP reference missing':'CSCOP reference missing',planKeys:byName.map(x=>x.key)};
 if(byName.length)return {coverage:'review',basis:'Project name found with a different or missing reference',planKeys:byName.map(x=>x.key)};
 return {coverage:'unplanned',basis:'No matching project in this domain’s current Q4 plan',planKeys:[]};
}
function reconcile(data){const plans=data.plans||[],labels=data.labels||[],sync=data.confluence||{},source=Array.isArray(sync.projects)?sync.projects:[],rows=plans.map(p=>({...p,domain:domain(p.domain),references:refs(p),coverage:'planned',basis:'Present in current domain Q4 source',origin:'planning',onePage:'pending',planKeys:[p.key]}));
 for(const p of labels){if(plans.some(x=>domain(x.domain)===domain(p.domain)&&names(x).some(n=>names(p).includes(n))))continue;const m=match(p,plans);if(m.coverage==='planned')continue;rows.push({...p,key:'register-'+(p.key||p.recordKey||p.id||rows.length),domain:domain(p.domain),references:refs(p),...m,origin:'register',onePage:'pending'});}
 const seenSource=new Map();
 for(const [i,p] of source.entries()){const identity=domain(p.domain)+'|'+refs(p).join(',')+'|'+name(p.name),previous=seenSource.get(identity);if(previous){if((previous.status||'')!==(p.status||'')||(previous.stage||'')!==(p.stage||'')){const row=rows.find(x=>x.confluence===previous);if(row){row.coverage='review';row.basis='Conflicting duplicate One Page records';row.onePageStatus='Not provided';row.onePageStage='Not provided';}}continue;}seenSource.set(identity,p);const m=match(p,plans),linked=m.planKeys.length?rows.filter(x=>x.origin==='planning'&&m.planKeys.includes(x.key)):[];
  if(m.coverage==='planned'&&linked.length===1){Object.assign(linked[0],{onePage:'verified',confluence:p,onePageStatus:p.status||'',onePageStage:p.stage||'',sourceUrl:p.sourceUrl||''});continue;}
  const register=rows.find(x=>x.origin==='register'&&domain(x.domain)===domain(p.domain)&&names(x).some(n=>names(p).includes(n)));
  const row={...p,key:'confluence-'+(p.key||i),domain:domain(p.domain),references:refs(p),...m,origin:'confluence',onePage:'verified',confluence:p,sourceUrl:p.sourceUrl||''};if(register)Object.assign(register,row);else rows.push(row);
 }
 const connected=(sync.domains||[]).filter(d=>d.status==='ready'&&d.complete===true&&d.asOf).map(d=>domain(d.name));
 for(const row of rows){const ds=(sync.domains||[]).find(d=>domain(d.name)===row.domain);row.syncAsOf=ds?.asOf||null;row.syncState=connected.includes(row.domain)?'ready':ds?.status==='stale'?'stale':'pending';if(row.origin==='planning'&&row.onePage==='pending'&&row.syncState==='ready')row.onePage='not-found';row.needsReview=row.coverage==='review'||!row.references.length||row.onePage==='not-found';}
 return {rows,connected,domainOrder:DOMAINS};
}
const GATES=[{key:'intake',name:'Intake',requirement:'BRD sign-off',checks:['brdSignOff']},{key:'feasibility',name:'Feasibility',requirement:'SOW signed',checks:['sowSigned']},{key:'dev',name:'Development',requirement:'Coding + TUAT completed',checks:['codingComplete','tuatComplete']},{key:'deploy',name:'Deploy',requirement:'Release completed',checks:['releaseComplete']},{key:'handover',name:'Handover',requirement:'Handover sign-off',checks:['handoverSignOff']}];
const isoDate=v=>{if(typeof v!=='string'||!/^\d{4}-\d{2}-\d{2}(?:T.*)?$/.test(v))return null;const d=v.slice(0,10),parsed=new Date(d+'T00:00:00Z');return Number.isFinite(+parsed)&&parsed.toISOString().slice(0,10)===d?d:null;};
function gateway(rows,gate,today){const values=rows.map(r=>({value:r.confluence?.gateways?.[gate.key]||r.gateways?.[gate.key]||{},row:r}));
 const supplied=values.filter(x=>Object.keys(x.value).length),dates=(key)=>[...new Set(supplied.map(x=>isoDate(x.value[key])).filter(Boolean))],planned=dates('plannedDate'),actual=dates('actualDate');
 if(!planned.length&&gate.key==='deploy')for(const r of rows){const date=isoDate(r.goLive);if(date&&!planned.includes(date))planned.push(date);}
 const evidence={};let conflict=planned.length>1||actual.length>1;
 // Completion must be documented together in one source record; never stitch
 // Coding from one conflicting project row to TUAT from another project.
 const completeRecords=supplied.filter(x=>gate.checks.every(c=>x.value.evidence?.[c]===true));
 for(const check of gate.checks){const states=[...new Set(supplied.map(x=>x.value.evidence?.[check]).filter(x=>typeof x==='boolean'))];if(states.length>1)conflict=true;evidence[check]=states.length===1?states[0]:null;}
 const projectNames=[...new Set(rows.map(r=>name(r.name)))],complete=completeRecords.length>0&&!conflict&&projectNames.every(n=>completeRecords.some(x=>name(x.row.name)===n)),plannedDate=planned.length===1?planned[0]:null,actualDate=actual.length===1?actual[0]:null,overdue=!!plannedDate&&plannedDate<today&&!complete&&!conflict;
 return {...gate,plannedDate,actualDate,plannedDates:planned,actualDates:actual,evidence,complete,conflict,overdue,status:conflict?'Review':complete?'Complete':overdue?'Past target':supplied.length||plannedDate||actualDate?'Pending':'Not provided',dateBasis:!dates('plannedDate').length&&planned.length&&gate.key==='deploy'?'Go-live target from domain source':'Explicit gateway date',sources:supplied.map(x=>({domain:x.row.domain,project:x.row.name,plannedDate:isoDate(x.value.plannedDate),actualDate:isoDate(x.value.actualDate),evidence:x.value.evidence||{}}))};
}
function control(data,today=new Date().toISOString().slice(0,10)){const reconciled=reconcile(data),groups=new Map();
 for(const r of reconciled.rows)for(const id of r.references){if(!groups.has(id))groups.set(id,[]);groups.get(id).push(r);}
 const known=v=>v&&v!=='To confirm'&&v!=='Not specified';
 const baseline=[...(data.plans||[]),...(data.labels||[])],findings=(data.confluence?.projects||[]).map(p=>{const ids=refs(p),same=new Set(baseline.filter(b=>domain(b.domain)===domain(p.domain)).flatMap(refs)),any=new Set(baseline.flatMap(refs)),missingReferences=ids.filter(id=>!any.has(id));return {...p,references:ids,missingReferences,presence:!ids.length?'review':ids.every(id=>same.has(id))?'present':missingReferences.length?'missing':'domain-review',planning:match(p,data.plans||[]).coverage};});
 const projects=[...groups].map(([id,rows])=>{const owning=rows.filter(r=>r.domain!=='SCM Ops'),primary=owning.length?owning:rows,allNames=[...new Set(primary.map(r=>r.name))],domains=[...new Set(rows.map(r=>r.domain))].sort((a,b)=>DOMAINS.indexOf(a)-DOMAINS.indexOf(b));
  const types=[...new Set(rows.map(r=>r.confluence?.demandSource||r.market||r.demandSource).filter(known))],intakes=[...new Set(rows.flatMap(r=>[r.confluence?.intakeNumber,r.intakeNumber,r.intake]).filter(v=>typeof v==='string'&&v.trim()&&/\d/.test(v)&&!/^(?:n\/?a|none|null|not provided|to confirm|tbd|tbc|pending|[-—])$/i.test(v.trim())).map(v=>v.trim()))];
  const statuses=[...new Set(primary.map(r=>r.onePageStatus||r.status).filter(known))],coverage=primary.some(r=>r.coverage==='review')?'review':primary.every(r=>r.coverage==='planned')?'planned':primary.some(r=>r.coverage==='planned')?'partial':'unplanned';
  const seenDetails=new Set(),allocations=(data.details||[]).filter(d=>refs({references:d.references}).includes(id)).filter(d=>{const key=JSON.stringify([d.domain,d.recordKey,d.person,d.role,d.sourceCell,d.md,d.project]);if(seenDetails.has(key))return false;seenDetails.add(key);return true;});
  const gateways=GATES.map(g=>gateway(primary,g,today)),related=findings.filter(p=>p.references.includes(id)),sharedEffort=allocations.some(d=>(d.references||[]).length>1);
  return {id,name:allNames[0],names:allNames,rows,primary,domains,types,intakes,hasIntake:intakes.length>0,status:statuses.length===1?statuses[0]:statuses.length?'Mixed source statuses':'Not provided',coverage,gateways,allocations,people:[...new Set(allocations.map(a=>a.person).filter(Boolean))],itemisedMD:allocations.some(a=>typeof a.md==='number')?Math.round(allocations.reduce((s,a)=>s+(typeof a.md==='number'?a.md:0),0)*100)/100:null,sharedEffort,onePage:related.length?'found':'unchecked',findings:related,needsReview:rows.some(r=>r.needsReview)||gateways.some(g=>g.conflict)||types.length>1,timelineMissing:gateways.some(g=>!g.plannedDate),overdue:gateways.some(g=>g.overdue),sourceOnly:related.some(p=>p.presence==='missing')&&coverage==='unplanned'};
 });
 return {projects,unreferenced:reconciled.rows.filter(r=>!r.references.length),findings,connected:reconciled.connected,rows:reconciled.rows};
}
return {DOMAINS,GATES,domain,refs,match,reconcile,isoDate,gateway,control};
});