(()=>{
'use strict';
const $=id=>document.getElementById(id);
let timer,deadline=0,attempt='',callbackReady=false;
async function post(path,body={}){
  const response=await fetch('/auth/wechat/'+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const data=await response.json();
  if(!response.ok)throw Error(data.error||'request_failed');
  return data;
}
function stop(){clearTimeout(timer);}
function enterDashboard(){stop();$('status').textContent='Sign-in successful. Opening dashboard…';location.replace('/summary/');}
async function poll(){
  if(Date.now()>deadline){$('status').textContent='QR code expired. Generate a new code.';return;}
  try{
    const response=await fetch('/auth/wechat/status?attempt='+encodeURIComponent(attempt),{cache:'no-store'});
    const data=await response.json();
    if(!response.ok)throw Error();
    if(data.status==='access_pending'||data.status==='access_denied'){
      stop();
      $('status').textContent=data.status==='access_denied'?'Access denied. Contact Nick Han.':'Waiting for Nick Han to approve your WeChat sign-in. No email entry is required.';
      return;
    }
    if(data.status==='approved'){
      const completed=await post('complete',{attempt});
      if(completed.authenticated!==true)throw Error();
      enterDashboard();return;
    }
    if(data.status==='failed'||data.status==='consumed')throw Error();
    $('status').textContent=data.status==='confirm'?'Confirm sign-in on your phone.':data.status==='authorizing'?'Verifying with WeChat…':'Waiting for scan…';
    timer=setTimeout(poll,data.status==='confirm'||data.status==='authorizing'?750:2000);
  }catch{$('status').textContent='Sign-in expired or unavailable. Generate a new code.';}
}
async function generate(){
  stop();$('generate').disabled=true;
  try{
    const data=await post('attempt');attempt=data.attempt;deadline=Date.now()+data.expiresIn*1000;
    const image=document.createElement('img');image.alt='Temporary WeChat sign-in QR code';
    image.src='/auth/wechat/qr?attempt='+encodeURIComponent(attempt);$('qrBox').replaceChildren(image);
    $('generate').textContent='Refresh QR code';
    $('status').textContent=callbackReady?'Waiting for scan…':'Preview only · cloud callback deployment pending';
    if(callbackReady)timer=setTimeout(poll,2000);
  }catch{$('status').textContent='Could not create a QR code. Please retry.';}
  finally{$('generate').disabled=false;}
}
$('generate').onclick=generate;
async function init(){
  $('generate').disabled=true;
  try{
    const [configResponse,meResponse]=await Promise.all([fetch('/auth/wechat/config',{cache:'no-store'}),fetch('/auth/wechat/me',{cache:'no-store'})]);
    if(!configResponse.ok||!meResponse.ok)throw Error();
    const [config,me]=await Promise.all([configResponse.json(),meResponse.json()]);
    if(me.authenticated===true){enterDashboard();return;}
    callbackReady=config.callbackDeployed===true;
    await generate();
  }catch{$('status').textContent='Sign-in service unavailable. Please retry.';$('generate').disabled=false;}
}
$('logout').onclick=async()=>{stop();await post('logout');location.reload();};
window.addEventListener('pagehide',stop);
init();
})();
