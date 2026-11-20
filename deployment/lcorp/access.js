(()=>{'use strict';
const $=id=>document.getElementById(id);let state,csrf='',busy=false;
const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
const formatDate=value=>value?new Date(value).toLocaleString([], {dateStyle:'medium',timeStyle:'short'}):'—';
function notice(text,error=false){$('notice').textContent=text;$('notice').className=error?'error':'';}
const errorText={admin_required:'Only Nick Han can manage access.',owner_protected:'The sole administrator cannot be disabled.',identity_already_bound:'This email is already linked to another approved WeChat identity.',email_not_allowed:'The company email is not enabled in the allowed list.',request_not_pending:'This request is not ready for approval.',csrf_required:'Your page has expired. Refresh and try again.',invalid_email:'Enter a valid full email address.',invalid_name:'Enter a full name of 2–80 characters.'};
async function api(path,body){const r=await fetch('/api/v1/access/'+path,{cache:'no-store',...(body?{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(body)}:{})});const data=await r.json();if(r.status===401){location.replace('/auth/wechat/login');throw Error('Sign in again.');}if(!r.ok)throw Error(errorText[data.error]||'The operation could not complete. Refresh and retry.');return data;}
async function load(){state=await api('list');csrf=state.csrf;render();}
async function update(payload,message){if(busy)return;busy=true;document.querySelectorAll('button').forEach(b=>b.disabled=true);try{await api('update',payload);await load();notice(message);}catch(e){notice(e.message,true);}finally{busy=false;document.querySelectorAll('button').forEach(b=>{if(b.dataset.locked!=='true')b.disabled=false;});}}
function button(text,handler,cls){const n=el('button',text,cls);n.type='button';n.onclick=handler;return n;}
function render(){
const all=state.members, pending=all.filter(m=>m.status==='pending');
$('pending-count').textContent=pending.length;$('approved-count').textContent=all.filter(m=>m.status==='approved').length;$('disabled-count').textContent=all.filter(m=>['revoked','rejected'].includes(m.status)).length;
const filter=$('filter').value;
const people=all.filter(m=>filter==='all'||filter==='pending'&&m.status==='pending'||filter==='approved'&&m.status==='approved'||filter==='disabled'&&['revoked','rejected'].includes(m.status));
$('people').replaceChildren();if(!people.length)$('people').append(el('div','No people in this view.','empty'));
people.forEach(m=>{
 const row=el('article',undefined,'person'),identity=el('div'),heading=el('h3',m.displayName||m.requestedName||'New WeChat sign-in');identity.append(heading,el('div',m.email||m.requestedEmail||'Awaiting administrator assignment','email'),el('div','Last scan · '+formatDate(m.lastSeen),'meta'));
 const status=el('div');status.append(el('span',({pending:'Pending review',approved:'Authorized',revoked:'Disabled',rejected:'Rejected'})[m.status]||m.status,'badge '+m.status));if(m.isAdmin)status.append(el('span','Sole admin','badge admin'));
 if(m.status==='pending')status.append(el('div','Confirm who just scanned, then assign an allowed person.','meta'));
 const actions=el('div',undefined,'actions');
 if(!m.isAdmin){
  if(m.status==='pending'||m.status==='revoked'){
   const choice=el('select',undefined,'assign-person');choice.setAttribute('aria-label','Assign this WeChat sign-in to an allowed person');
   const placeholder=el('option','Choose allowed person…');placeholder.value='';choice.append(placeholder);
   state.allowlist.filter(a=>a.enabled&&!a.isOwner&&!all.some(other=>other.status==='approved'&&other.email===a.email&&other.requestCode!==m.requestCode)).forEach(a=>{const option=el('option',a.displayName+' · '+a.email);option.value=a.email;choice.append(option);});
   identity.append(choice);
   const approve=button(m.status==='revoked'?'Re-enable':'Approve',()=>{const person=state.allowlist.find(a=>a.email===choice.value);if(!person)return;if(confirm('Confirm this WeChat sign-in belongs to '+person.displayName+' ('+person.email+') and grant dashboard access?'))update({action:'approve',requestCode:m.requestCode,email:person.email},'Access approved. The user can scan again to sign in.');});
   approve.disabled=true;approve.dataset.locked='true';choice.onchange=()=>{approve.disabled=busy||!choice.value;approve.dataset.locked=choice.value?'false':'true';};actions.append(approve);
  }
  if(m.status==='pending')actions.append(button('Reject',()=>{if(confirm('Reject this access request?'))update({action:'reject',requestCode:m.requestCode},'Request rejected.');},'secondary'));
  if(m.status==='approved')actions.append(button('Disable access',()=>{if(confirm('Disable dashboard access for '+(m.displayName||m.email)+'? Existing sessions will no longer grant access.'))update({action:'revoke',requestCode:m.requestCode},'Access disabled.');},'danger'));
 }else actions.append(el('span','Protected owner','meta'));
 row.append(identity,status,actions);$('people').append(row);
});
$('allowlist').replaceChildren();state.allowlist.forEach(m=>{const row=el('div',undefined,'allow-row'),identity=el('div');identity.append(el('strong',m.displayName),el('div',m.email,'email'));const actions=el('div',undefined,'actions');
 if(m.isOwner)actions.append(el('span','Owner · always enabled','badge admin'));
 else if(m.enabled)actions.append(button('Disable email',()=>{if(confirm('Disable '+m.email+' and revoke any active dashboard access for this email?'))update({action:'disable_email',email:m.email},'Email disabled and existing access revoked.');},'secondary'));
 else actions.append(button('Enable',()=>update({action:'allow',email:m.email,displayName:m.displayName},'Email enabled for new requests.'),'secondary'));
 row.append(identity,actions);$('allowlist').append(row);
});
$('audit').replaceChildren();state.audit.forEach(a=>$('audit').append(el('div',formatDate(a.changedAt)+' · '+a.action.replaceAll('_',' ')+' · '+(a.actorEmail||'Applicant'),'audit-row')));
}
$('filter').onchange=()=>state&&render();$('refresh').onclick=()=>load().catch(e=>notice(e.message,true));
$('allow-form').onsubmit=e=>{e.preventDefault();update({action:'allow',email:$('allow-email').value.trim().toLowerCase(),displayName:$('allow-name').value.trim()},'Email added. The user must still submit a WeChat access request.');};
$('signout').onclick=async()=>{await fetch('/auth/wechat/logout',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});location.replace('/auth/wechat/login');};
load().catch(e=>{notice(e.message,true);$('people').replaceChildren(el('div','This page requires Nick Han’s administrator session.','empty'));});
})();
