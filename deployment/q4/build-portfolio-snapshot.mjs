import {readFile,writeFile} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import {createHash} from 'node:crypto';
import vm from 'node:vm';
const repo=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const site=path.join(repo,'public');
const routes=['corporate','mpa','fulfillment','upstream-scm-mdm','q4-ops'];
function dataset(html,id='data'){
 const match=html.match(new RegExp('<script id="'+id+'" type="application/json">([\\s\\S]*?)<\\/script>'));
 if(!match)throw Error('Dataset missing: '+id);return JSON.parse(match[1]);
}
const summaryPath=path.join(site,'summary/index.html');
let summary=await readFile(summaryPath,'utf8');
const sources=Object.fromEntries(await Promise.all(routes.map(async route=>[route,dataset(await readFile(path.join(site,route,'index.html'),'utf8'))])));
const qa=dataset(await readFile(path.join(site,'qa/index.html'),'utf8'),'qa-plan');
const labels=dataset(await readFile(path.join(site,'project-labels/index.html'),'utf8'),'labels-data');
const start=summary.indexOf('const SummaryCore='),end=summary.indexOf('\nfunction projectRef',start);
if(start<0||end<start)throw Error('Summary calculation module missing');
const context=vm.createContext({sources,console,document:{querySelector:selector=>selector.includes('#qa-plan')?{textContent:JSON.stringify(qa)}:null},fetch:()=>{throw Error('Snapshot generation must not access the network')}});
// Execute the existing browser calculations, including Finance and authoritative final QA.
const calculate=[
 '(async()=>{const ds=PlanningData.createDomains();',
 "for(const d of ds)PlanningData.ingest(d,sources[d.id==='omni'?'fulfillment':d.id]);",
 'PlanningData.applyFinance(ds);await PlanningData.applyQA(ds);',
 "if(ds.some(d=>d.status!=='ready'||d.qaPlanStatus!=='ready'))throw Error('Incomplete portfolio sources');",
 'return ds;})()'
].join('\n');
const domains=await vm.runInContext(summary.slice(start,end)+'\n'+calculate,context,{timeout:10000});
const labelFields=['recordKey','id','references','name','market','domain','type','typeStatus','status'];
const compactDomain=({id,name,url,status,projectCount,asOf,message,resources,partialAllocations,qaPlanStatus})=>({id,name,url,status,projectCount,asOf,message,resources,partialAllocations:!!partialAllocations,qaPlanStatus,roster:[]});
const bundle={schemaVersion:1,revision:createHash('sha256').update(JSON.stringify({sources,qa,labels})).digest('hex').slice(0,20),domains:JSON.parse(JSON.stringify(domains.map(compactDomain))),labels:{projects:labels.projects.map(p=>Object.fromEntries(labelFields.filter(k=>Object.hasOwn(p,k)).map(k=>[k,p[k]])))}};
const resourceBundle={...bundle,domains:domains.map(d=>({...compactDomain(d),roster:d.roster.map(r=>r.planReady&&d.resources.some(x=>x.key===r.key)?{resourceRef:true,key:r.key,...(Object.hasOwn(r,'rawProjects')?{rawProjects:r.rawProjects}:{})}:r)}))};
const qaResource=r=>r.category==='Shared QA'||(r.roles||[]).some(role=>/^QA(?:\s+Lead)?$/i.test(role));
const qaBundle={...bundle,domains:domains.map(d=>({...compactDomain(d),resources:d.resources.filter(qaResource),raw:{allocations:(d.raw?.allocations||[]).filter(a=>a.role==='QA'&&a.category==='Unassigned'&&a.md>0)}}))};
const total=bundle.domains.flatMap(d=>d.resources).reduce((s,r)=>s+(typeof r.md==='number'?r.md:0),0);
if(!Number.isFinite(total)||total<=0)throw Error('Invalid portfolio total');
const serialized=JSON.stringify(bundle).replaceAll('<','\\u003c');
const tag='<script id="portfolio-snapshot" type="application/json">'+serialized+'</script>';
const existing=/<script id="portfolio-snapshot" type="application\/json">[\s\S]*?<\/script>/;
summary=existing.test(summary)?summary.replace(existing,()=>tag):summary.replace('</head>',tag+'</head>');
await writeFile(summaryPath,summary);
await writeFile(path.join(site,'assets/portfolio-data.json'),serialized+'\n');
await writeFile(path.join(site,'assets/project-label-data.json'),JSON.stringify(bundle.labels).replaceAll('<','\\u003c')+'\n');
function embed(html,id,value){const content=JSON.stringify(value).replaceAll('<','\\u003c'),tag='<script id="'+id+'" type="application/json">'+content+'</script>',existing=new RegExp('<script id="'+id+'" type="application/json">[\\s\\S]*?<\\/script>');return existing.test(html)?html.replace(existing,()=>tag):html.replace('</head>',tag+'</head>');}
for(const [route,id,value,file]of [['resources','resources-snapshot',resourceBundle,'resource-list-data.json'],['qa','qa-snapshot',qaBundle,'qa-data.json']]){
 const filePath=path.join(site,route,'index.html');await writeFile(filePath,embed(await readFile(filePath,'utf8'),id,value));await writeFile(path.join(site,'assets',file),JSON.stringify(value).replaceAll('<','\\u003c')+'\n');
}
for(const route of ['corporate','mpa','fulfillment','upstream-scm-mdm','q4-ops','q4-ops-plan-b']){const filePath=path.join(site,route,'index.html');await writeFile(filePath,embed(await readFile(filePath,'utf8'),'portfolio-labels',bundle.labels));}
// Export the complete project register, including projects without named effort.
// Keep separate source project rows even when they share a CSCOP reference.
const clean=s=>String(s||'').trim().toLowerCase().replace(/[^a-z0-9]/g,'');
const refs=p=>[...new Set([p.id,p.projectId,...(p.references||[])].filter(Boolean).flatMap(s=>{const out=[];for(const m of String(s).matchAll(/\b(?:CSCOP|CDM)-(\d+(?:\/\d+)*)/gi))for(const n of m[1].split('/'))out.push('CSCOP-'+n);return out;}))];
const exportDomain=name=>name==='Supplychain SCM&MDM'?'Upstream SCM & MDM':name;
const exportProjects=labels.projects.filter(p=>refs(p).length).map(p=>({...p,domain:exportDomain(p.domain),references:refs(p)}));
const domainNames=Object.fromEntries(domains.map(d=>[d.id,d.name]));
for(const [route,source]of Object.entries(sources)){
 const domain=domainNames[route==='fulfillment'?'omni':route];
 for(const p of source.projects||source.items||[]){
  if(!refs(p).length)continue;
  const match=exportProjects.find(x=>x.domain===domain&&clean(x.name)===clean(p.name));
  if(!match)exportProjects.push({id:refs(p)[0],references:refs(p),name:p.name,domain,status:'',sourceStage:p.stage||'',market:p.market||'',type:p.type||'',typeStatus:'',recordKey:route+'-'+(p.row||p.key||p.name)});
 }
}
const exportDetails=[];
for(const d of domains)for(const r of d.resources)for(const p of r.projects||[]){
 if(!refs(p).length)continue;
 const candidates=exportProjects.filter(x=>x.domain===d.name&&x.references.some(id=>refs(p).includes(id)));
 let project=candidates.find(x=>clean(x.name)===clean(p.name)||(x.aliases||[]).some(a=>clean(a)===clean(p.name)));
 if(!project&&candidates.length===1)project=candidates[0];
 if(!project){project={id:refs(p)[0],references:refs(p),name:p.name,domain:d.name,status:'',market:'',type:'',recordKey:d.id+'-'+p.name};exportProjects.push(project);}
 exportDetails.push({references:refs(p),project:p.name,recordKey:project.recordKey||project.id,domain:d.name,person:r.name,role:p.role||'',category:r.category,md:typeof p.md==='number'?p.md:null,sourceCell:p.sourceCell||'',note:p.note||''});
}
await writeFile(path.join(site,'assets/cscop-export-data.json'),JSON.stringify({revision:bundle.revision,projects:exportProjects.map(p=>({key:p.recordKey||p.id,references:p.references,name:p.name,domain:p.domain,status:p.status||'',sourceStage:p.sourceStage||'',demandSource:p.market==='To confirm'?'':p.market||'',demandType:p.type||'',labelStatus:p.typeStatus||''})),details:exportDetails}).replaceAll('<','\\u003c')+'\n');
// Inventory and plan coverage are separate from personnel totals. No network calls.
const overviewPlans=[];
for(const [route,source]of Object.entries(sources)){
 const domain=domainNames[route==='fulfillment'?'omni':route];
 for(const [i,p]of(source.projects||source.items||[]).entries()){
  const label=labels.projects.find(l=>exportDomain(l.domain)===domain&&[l.name,...(l.aliases||[])].some(n=>clean(n)===clean(p.name)));
  overviewPlans.push({...label,...p,key:route+'-'+(p.key||p.row||i),domain,references:refs(p),status:label?.status||'To confirm',sourceStage:p.stage||label?.sourceStage||'',sources:label?.sources||[source.source||'Domain planning source'],market:p.market||label?.market||'',type:p.type||label?.type||'',typeStatus:label?.typeStatus||'Suggested from project source'});
 }
}
const overviewDetails=exportDetails.map(d=>{const exact=overviewPlans.filter(p=>p.domain===d.domain&&clean(p.name)===clean(d.project));return {...d,recordKey:exact.length===1?exact[0].key:d.recordKey};});
const confluence=JSON.parse(await readFile(path.join(site,'assets/confluence-onepage-data.json'),'utf8'));
if(confluence.schemaVersion!==1||!Array.isArray(confluence.domains)||!Array.isArray(confluence.projects))throw Error('Invalid One Page snapshot contract');
for(const p of confluence.projects)if(!p.name||!['Corporate','MP&A','Fulfillment','Upstream SCM & MDM','SCM Ops'].includes(p.domain))throw Error('One Page project requires a known owning domain and project name');
const overview={schemaVersion:1,revision:bundle.revision,asOf:'Source dates retained',plans:overviewPlans,labels:labels.projects.map(p=>({...p,domain:exportDomain(p.domain)})),details:overviewDetails,confluence:{...confluence,projects:[]}};
await writeFile(path.join(site,'assets/portfolio-overview-data.json'),JSON.stringify(overview).replaceAll('<','\\u003c')+'\n');
console.log(JSON.stringify({status:'PASS',domains:domains.length,revision:bundle.revision,totalMD:Math.round(total*100)/100,snapshotBytes:Buffer.byteLength(serialized)}));
