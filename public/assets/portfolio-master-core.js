(function(root,factory){if(typeof module==='object'&&module.exports)module.exports=factory();else root.PortfolioMasterCore=factory();})(typeof window==='undefined'?this:window,function(){'use strict';
const DOMAINS=['Corporate','MP&A','Fulfillment','Upstream SCM & MDM','SCM Ops'];
const normalize=s=>String(s||'').normalize('NFKC').toLowerCase().replace(/[^a-z0-9\u4e00-\u9fff]/g,'');
function references(p){return [...new Set([...(p.references||[]),p.id||''].flatMap(s=>{const out=[];for(const m of String(s).matchAll(/\b(CSCOP|CDM)-(\d+(?:-\d+)?(?:\/\d+(?:-\d+)?)*)/gi))for(const n of m[2].split('/'))out.push(m[1].toUpperCase()==='CDM'&&!['3960','3961'].includes(n)?'CDM-'+n:'CSCOP-'+n);return out;}))];}
function reconcile(master,onepage){
 const ready=master?.status==='ready'&&master.complete===true&&!!master.asOf;
 if(!ready)return {ready:false,rows:[],counts:null,asOf:master?.asOf||null};
 const pages=onepage.projects||[],verified=new Set((onepage.domains||[]).filter(d=>d.status==='ready'&&d.complete&&d.asOf).map(d=>d.name));
 const child=id=>/^(?:CSCOP|CDM)-\d+-\d+$/.test(id);
 const ignored=(master.projects||[]).filter(p=>references(p).length&&references(p).every(child));
 const rows=(master.projects||[]).filter(p=>!ignored.includes(p)).map(p=>{
  const ids=references(p).filter(id=>!child(id)),sameDomain=pages.filter(x=>x.domain===p.domain),sameName=sameDomain.filter(x=>normalize(x.name)===normalize(p.name)),idHits=sameDomain.filter(x=>references(x).some(id=>ids.includes(id))),exact=idHits.filter(x=>normalize(x.name)===normalize(p.name)),allDomainHits=pages.filter(x=>references(x).some(id=>ids.includes(id)));
  let state,reason,hits=[];
  if(!DOMAINS.includes(p.domain)){state='review';reason='Owning domain not mapped to the five-domain scope';}
  else if(!verified.has(p.domain)){state='unverified';reason='Owning-domain One Page snapshot is unavailable or incomplete';}
  else if(!ids.length){state='review';reason='Master record has no CSCOP reference';hits=sameName;}
  else if(exact.length&&ids.every(id=>exact.some(x=>references(x).includes(id)))){state='present';reason='Domain + CSCOP + project name agree';hits=exact;}
  else if(idHits.length){state='review';reason='CSCOP exists, but project names or reference coverage differ';hits=idHits;}
  else if(sameName.length){state='review';reason='Project name exists with a different or missing CSCOP';hits=sameName;}
  else if(allDomainHits.length){state='review';reason='CSCOP found in a different domain; verify ownership';hits=allDomainHits;}
  else{state='missing';reason='Master CSCOP and project name were not found in the owning-domain One Page';}
  return {...p,references:ids,state,reason,onePageMatches:hits.map(x=>({key:x.key,name:x.name,domain:x.domain,status:x.status,sourceUrl:x.sourceUrl,source:x.source}))};
 });
 return {ready:true,rows,asOf:master.asOf,ignoredNonJiraRows:(master.ignoredNonJiraRows||0)+ignored.length,counts:Object.fromEntries(['present','missing','review','unverified'].map(s=>[s,rows.filter(r=>r.state===s).length]))};
}
return {DOMAINS,normalize,references,reconcile};
});
