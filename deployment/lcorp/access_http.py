"""Owner-only access-management HTTP routes."""
import hashlib
import hmac
import json
from pathlib import Path
from auth import AuthError
ROOT=Path(__file__).resolve().parent
class AccessMixin:
 def admin_csrf(self):
  return hmac.new(self.server.auth.key.encode(),('access-csrf|'+self.cookie('wx_session')).encode(),hashlib.sha256).hexdigest()
 def access_get(self,path):
  if self.server.auth is None:return self.send(503,{'error':'login_service_unavailable'})
  try:
   user=self.server.auth.user(self.cookie('wx_session'))
   if path=='/api/v1/access/me':return self.send(200,{'authenticated':bool(user),'isAdmin':bool(user and user.get('isAdmin'))})
   if not user:
    if path.startswith('/api/'):return self.send(401,{'error':'authentication_required'})
    return self.send(302,b'',headers=[('Location','/auth/wechat/login')])
   # Check the anchored administrator at the database on every admin request.
   self.server.auth.admin('me',self.cookie('wx_session'))
   if path=='/api/v1/access/list':
    data=self.server.auth.admin('list',self.cookie('wx_session'));data['csrf']=self.admin_csrf()
    return self.send(200,data)
   if path=='/access':return self.send(308,b'',headers=[('Location','/access/')])
   files={'/access/':('access.html','text/html'),'/access/style.css':('access.css','text/css'),'/access/app.js':('access.js','text/javascript')}
   if path not in files:return self.send(404,{'error':'not_found'})
   name,mime=files[path];return self.send(200,(ROOT/name).read_bytes(),mime+'; charset=utf-8')
  except AuthError as e:
   return self.send(403 if str(e)=='admin_required' else 503,{'error':'admin_required' if str(e)=='admin_required' else 'access_service_unavailable'})
  except Exception:return self.send(503,{'error':'access_service_unavailable'})
 def access_post(self,path):
  if self.headers.get('Origin')!=self.server.origin:return self.send(403,{'error':'origin_not_allowed'})
  if self.headers.get('Content-Type','').split(';')[0]!='application/json':return self.send(415,{'error':'json_required'})
  try:
   size=int(self.headers.get('Content-Length','0'))
   if not 0<size<=4096:return self.send(413,{'error':'request_too_large'})
   data=json.loads(self.rfile.read(size));assert isinstance(data,dict)
   if self.server.auth is None:return self.send(503,{'error':'access_service_unavailable'})
   self.server.auth.admin('me',self.cookie('wx_session'))
   if not hmac.compare_digest(self.headers.get('X-CSRF-Token',''),self.admin_csrf()):return self.send(403,{'error':'csrf_required'})
   if path!='/api/v1/access/update':return self.send(404,{'error':'not_found'})
   action=data.get('action');payload={}
   if action in ('approve','reject','revoke'):
    payload['request_code']=data.get('requestCode','')
    if action=='approve':payload['email']=data.get('email','')
   elif action in ('allow','disable_email'):
    payload['email']=data.get('email','');payload['display_name']=data.get('displayName','')
   else:return self.send(400,{'error':'invalid_action'})
   if any(not isinstance(v,str) or len(v)>254 for v in payload.values()):return self.send(400,{'error':'invalid_input'})
   return self.send(200,self.server.auth.admin(action,self.cookie('wx_session'),**payload))
  except AuthError as e:
   public={'admin_required','owner_protected','email_not_allowed','request_not_pending','identity_already_bound','request_not_found','invalid_email','invalid_name'}
   return self.send(403 if str(e)=='admin_required' else 400,{'error':str(e) if str(e) in public else 'access_service_unavailable'})
  except Exception:return self.send(400,{'error':'invalid_request'})
