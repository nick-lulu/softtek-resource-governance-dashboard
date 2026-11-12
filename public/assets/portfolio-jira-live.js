(()=>{'use strict';let timer,busy=false,started=false,latest,onUpdate,quickChecks=0;
function schedule(ms){clearTimeout(timer);timer=setTimeout(poll,ms);}
async function poll(){
 if(busy||document.hidden){schedule(60000);return;}
 busy=true;const abort=new AbortController(),timeout=setTimeout(()=>abort.abort(),55000);
 onUpdate({...latest,sync:{...latest.sync,state:'updating'}});
 try{
  const r=await fetch('/api/v1/portfolio/jira',{cache:'no-store',signal:abort.signal});
  if(!r.ok)throw Error();const next=await r.json();
  if(next.sourceType!=='jira'||next.status!=='ready'||next.complete!==true||!Array.isArray(next.projects)||!next.sync)throw Error();
  latest=next;onUpdate(next);
  if(next.sync.state==='updating'&&quickChecks++<10)schedule(3000);else{quickChecks=0;schedule(60000);}
 }catch{onUpdate({...latest,sync:{...latest.sync,state:'stale'}});schedule(60000);}
 finally{clearTimeout(timeout);busy=false;}
}
window.PortfolioJiraLive={start(snapshot,callback){latest=snapshot;onUpdate=callback;clearTimeout(timer);quickChecks=0;
 if(location.hostname.endsWith('github.io'))return;
 if(!started){document.addEventListener('visibilitychange',()=>{if(!document.hidden)poll();});started=true;}
 poll();
}};
})();
