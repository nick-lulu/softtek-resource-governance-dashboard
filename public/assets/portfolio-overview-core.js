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
return {DOMAINS,domain,refs,match,reconcile};
});