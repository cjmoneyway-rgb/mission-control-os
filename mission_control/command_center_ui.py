"""Local browser presentation over the existing synthetic gateway; no domain store."""
from dataclasses import dataclass
from datetime import datetime, timezone
import re
from pathlib import Path
import hmac
import secrets
import threading
import time

from .connection_contracts import COMMAND_STAGES, CONNECTORS, MAX_REQUEST_BYTES, ROUTES, WRITE_ACTIONS, decode_request, validate_projection, validate_command_center, validate_eligibility
from .connection_gateway import Gateway, LocalContext, SyntheticPolicyGate, Budget, RateExceeded
from .json_io import strict_json_loads
from .local_http import LocalHTTPServer, SyntheticBinding, SECURITY_HEADERS, _Handler
from .synthetic_identity import SyntheticAuthority, canonical_bytes, fingerprint

ROOT = '/command-center'
COOKIE = 'mc_ceo_session'
ASSET_ROOT = Path(__file__).with_name('command_center_assets')
ASSETS = {ROOT: ('index.html','text/html; charset=utf-8'),
          ROOT+'/app.css': ('app.css','text/css; charset=utf-8'),
          ROOT+'/app.js': ('app.js','text/javascript; charset=utf-8')}
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
       "frame-ancestors 'none'; base-uri 'none'; form-action 'self'")


@dataclass(frozen=True)
class UIConfig:
    """Trusted startup candidates, not claims accepted from browser payloads.

    All envelopes are decoded and reauthorized on every use. No browser-selected
    tenant, role, identity, route, domain payload or approval evidence is admitted.
    """
    reads: tuple[bytes, ...] = ()
    actions: tuple[bytes, ...] = ()


def fresh(raw):
    value = strict_json_loads(raw.decode('utf-8'))
    value['timestamp'] = datetime.now(timezone.utc).isoformat()
    return value


class LocalCEOInterface(LocalHTTPServer):
    """Disabled by default. Explicit installed fixture authority, exact 127.0.0.1."""
    def __init__(self, gateway=None, binding=None, config=None, *, synthetic_development=False,
                 host='127.0.0.1', port=0, timeout_seconds=2, session_seconds=300):
        if synthetic_development is not True:
            raise PermissionError('Explicit synthetic-development flag required')
        if host != '127.0.0.1':
            raise ValueError('Literal 127.0.0.1 required')
        if (type(gateway) is not Gateway or type(gateway.gate) is not SyntheticPolicyGate
                or type(gateway.gate.authority) is not SyntheticAuthority or
                any(value is None for value in (gateway.services,gateway.audit_sink,gateway.rate_limit))
                or type(binding) is not SyntheticBinding or type(config) is not UIConfig):
            raise PermissionError('Installed synthetic authority required')
        if type(session_seconds) is not int or not 1 <= session_seconds <= 300:
            raise ValueError('Short-lived session required')
        if type(config.reads) is not tuple or type(config.actions) is not tuple or len(config.reads)+len(config.actions)>32:
            raise ValueError('Bounded trusted fixture candidates required')
        self.reads, self.actions = {}, {}
        for collection, destination, allowed in ((config.reads,self.reads,{'visibility.project','journey.read','readiness.status','routing.preview'}),
                                                (config.actions,self.actions,WRITE_ACTIONS)):
            for index, raw in enumerate(collection):
                request=decode_request(canonical_bytes(fresh(raw)))
                if request.requested_action not in allowed:
                    raise ValueError('Unsupported UI action')
                if request.authentication_state_reference != binding.session_reference:
                    raise PermissionError('Server-held identity binding required')
                # Verify real configured identity and exact policy before listener creation.
                gateway.gate.verify(request,LocalContext(binding.session_reference,binding.policy_revision))
                destination['syn-ui-'+('read' if destination is self.reads else 'action')+'-'+str(index+1)] = bytes(raw)
        if not self.reads and not self.actions:
            raise ValueError('Explicit synthetic candidates required')
        for connector in CONNECTORS: connector.validate()
        self.identity_template = next(iter((*self.reads.values(), *self.actions.values())))
        self.binding, self.config = binding, config
        self.session_seconds=session_seconds
        self.sessions={}
        super().__init__(gateway,(binding,),synthetic_development=True,host=host,port=port,timeout_seconds=timeout_seconds)
        self.RequestHandlerClass=_UIHandler

    def shutdown(self):
        try:
            super().shutdown()
        finally:
            self.sessions.clear()

    def server_close(self):
        self.sessions.clear()
        super().server_close()

    def authorize_session(self):
        request=decode_request(canonical_bytes(fresh(self.identity_template)))
        self.gateway.gate.verify(request,LocalContext(self.binding.session_reference,self.binding.policy_revision))

    def session(self, header):
        self.authorize_session()
        if type(header) is not str or len(header)>128:
            raise PermissionError('Session required')
        if not re.fullmatch(COOKIE+r'=[0-9a-f]{64}',header):
            raise PermissionError('Session required')
        key=header.split('=',1)[1]
        session=self.sessions.get(key)
        if session is None or session['expires']<=time.monotonic():
            self.sessions.pop(key,None)
            raise PermissionError('Session required')
        return session

    def open_session(self, header):
        self.authorize_session()
        try:
            return None,self.session(header)
        except PermissionError:
            self.sessions={key:value for key,value in self.sessions.items() if value['expires']>time.monotonic()}
            if len(self.sessions)>=16: raise PermissionError('Session capacity')
            key=secrets.token_hex(32)
            value=dict(expires=time.monotonic()+self.session_seconds,csrf=secrets.token_hex(32),intents={})
            self.sessions[key]=value
            return key,value

    def call(self, raw):
        request=decode_request(raw)
        route=next(((method,path) for (method,path),action in ROUTES.items()
                    if action==request.requested_action and '{' not in path),None)
        if request.requested_action=='journey.read': route=('GET','/v1/journeys/'+request.resource_reference)
        if route is None: raise PermissionError('Unsupported route')
        context=LocalContext(self.binding.session_reference,self.binding.policy_revision)
        timer=threading.Timer(self.timeout_seconds,context.cancelled.set);timer.daemon=True;timer.start()
        try:
            code, body=self.gateway.handle(*route,raw,context)
        finally:
            timer.cancel()
        # Never expose malformed output or trust unexpected backend declarations.
        if (type(body) is not dict or body.get('state')!='inactive' or body.get('operational_authorized') is not False):
            raise ValueError('Invalid projection')
        if type(code) is not int or code not in (200,400,403,404,408,409,429,503):
            raise ValueError('Invalid response status')
        if code==200:
            result=validate_projection(body.get('result'))
            required={
                'journey.read':{'state','journey_reference','original_classification','version','completed_stage','events'},
                'visibility.project':{'state','packet_reference','revision','source_event_reference','original_classification','current_classification','executive_reference','department_references','audience'},
                'routing.preview':{'state','packet_references','original_classification'},
                'readiness.status':{'state','synthetic_ready','operational_authorized','verified_controls'},
                'intake':{'state','journey_reference','intake_reference','original_classification','version'},
                'decision.submit':{'state','status','event_reference','revision','journey_reference'},
                'work-packet.create':{'state','journey_reference','event_reference','version','status','packet_references'},
                'assignment.acknowledge':{'state','packet_reference','revision'},
                'handoff.record':{'state','packet_reference','revision'},
                'outcome.record':{'state','packet_reference','revision'},
            }.get(request.requested_action)
            if required is None or set(result)!=required:
                raise ValueError('Incomplete projection')
            if request.requested_action in ('journey.read','intake') and (
                    result['journey_reference']!=request.resource_reference or result['version']!=request.expected_revision):
                raise ValueError('Projection binding mismatch')
            if request.requested_action=='visibility.project' and (
                    result['packet_reference']!=request.resource_reference or result['revision']!=request.expected_revision
                    or result['source_event_reference']!=request.correlation_reference or result['audience']!='command'):
                raise ValueError('Projection binding mismatch')
        return code,body

    def governed(self, method, request):
        decision=self.gateway.gate.verify(request,LocalContext(self.binding.session_reference,self.binding.policy_revision))
        self.gateway.rate_limit.admit(request.tenant_reference,request.actor_reference)
        audit_ref='syn-ui-audit-'+fingerprint([request.request_id,decision,method])
        self.gateway.audit_sink.append(dict(audit_event_reference=audit_ref,request_id=request.request_id,
            correlation_reference=request.correlation_reference,tenant_reference=request.tenant_reference,actor_reference=request.actor_reference,
            action='command-center.project' if method=='command_center' else 'eligibility.evaluate',authorization_decision_reference=decision,
            policy_revision=self.binding.policy_revision,timestamp=datetime.now(timezone.utc).isoformat(),decision='authorized_attempt',schema_version=1))
        context=LocalContext(self.binding.session_reference,self.binding.policy_revision)
        budget=Budget(context,self.timeout_seconds)
        timer=threading.Timer(self.timeout_seconds,context.cancelled.set);timer.daemon=True;timer.start()
        try:
            function=getattr(self.gateway.services,method,None)
            if not callable(function):raise ValueError('Governed service unavailable')
            value=function(request,context,budget);budget.check()
            return validate_eligibility(value,request) if method=='eligibility' else validate_command_center(value)
        finally:timer.cancel()

    def eligibility_for(self,raw):
        return self.governed('eligibility',decode_request(raw))

    @staticmethod
    def eligibility_denial(eligibility):
        codes=eligibility['blocker_codes']
        status=400 if 'eligibility_unavailable' in codes else (403 if 'authorization_denied' in codes else 409)
        return Gateway._error(status,'dependencies_unresolved' if 'unresolved_dependencies' in codes else 'eligibility_denied')

    def overview(self, session):
        items=[];readiness=None
        for reference,raw in self.reads.items():
            value=fresh(raw);code,body=self.call(canonical_bytes(value))
            if code!=200:
                continue  # No denied reference, tenant or reason is projected.
            result=body['result']
            if value['requested_action']=='readiness.status': readiness=result
            else: items.append(dict(view_reference=reference,kind=value['requested_action'],projection=result))
        governed=self.governed('command_center',decode_request(canonical_bytes(fresh(self.identity_template))))
        return dict(schema_version=1,state='inactive',operational_authorized=False,queues=governed['queues'],blocked_count=sum(queue['blocked_count'] for queue in governed['queues']),
            stages=list(COMMAND_STAGES),items=items,readiness=readiness,
            counts=dict(authorized_views=len(items),
                information=None,intelligence=None,decision=None,assignment=None,execution=None,measurement=None,blocked=None),
            # No six-stage classification/count API exists in Phase 2A. Unknown is not zero.
            unavailable_fields=[],
            actions=self.allowed_actions(),csrf_token=session['csrf'],connectors_disabled=len(CONNECTORS))

    def allowed_actions(self):
        actions=[]
        for key,raw in self.actions.items():
            request=decode_request(canonical_bytes(fresh(raw)))
            try:
                self.gateway.gate.verify(request,LocalContext(self.binding.session_reference,self.binding.policy_revision))
            except PermissionError:
                continue
            eligibility=self.eligibility_for(canonical_bytes(fresh(raw)))
            actions.append(dict(action_reference=key,requested_action=request.requested_action,eligibility=eligibility))
        return actions

    def prepare(self,session,body):
        if set(body)!={'action_reference','csrf_token'}: raise ValueError('Exact prepare schema required')
        self.csrf(session,body['csrf_token'])
        reference=body['action_reference']
        if type(reference) is not str or reference not in self.actions: raise PermissionError('Denied')
        prior=session['intents'].get(reference)
        if prior:
            if prior['used'] or prior['expires']<=time.monotonic(): return 409,Gateway._error(409,'confirmation_expired_or_used')[1]
            return 200,prior['confirmation']
        value=fresh(self.actions[reference]);value['request_id']='syn-ui-request-'+secrets.token_hex(12)
        value['idempotency_key']='syn-ui-key-'+secrets.token_hex(12)
        value['source_surface']='syn-command-center'
        raw=canonical_bytes(value);request=decode_request(raw)
        self.gateway.gate.verify(request,LocalContext(self.binding.session_reference,self.binding.policy_revision))
        eligibility=self.eligibility_for(raw)
        if not eligibility['eligible']:return self.eligibility_denial(eligibility)
        projection=self.governed('command_center',request)
        target=next((item for queue in projection['queues'] for item in queue['items'] if item['reference']==request.resource_reference),None)
        department=target['owning_department_reference'] if target else None
        csrf=secrets.token_hex(32)
        confirmation=dict(schema_version=1,state='inactive',operational_authorized=False,
            requested_action=request.requested_action,target_reference=request.resource_reference,eligibility=eligibility,
            request_reference=request.request_id,idempotency_key=request.idempotency_key,
            expected_revision=request.expected_revision,owning_department_reference=department,dependencies=[],dependency_state='resolved',
            technical_consequences='Apply the existing synthetic service transaction only; no organizational approval, operational routing or delivery.',
            warning='This action remains synthetic and inactive.',csrf_token=csrf)
        session['intents'][reference]=dict(raw=raw,csrf=csrf,expires=time.monotonic()+60,used=False,confirmation=confirmation)
        return 200,confirmation

    @staticmethod
    def csrf(session,token):
        if type(token) is not str or len(token)!=64 or not token.isascii() or not hmac.compare_digest(token,session['csrf']):
            raise PermissionError('CSRF required')

    def confirm(self,session,body):
        if set(body)!={'request_reference','idempotency_key','expected_revision','csrf_token','confirmed'}:
            raise ValueError('Exact confirmation schema required')
        if body['confirmed'] is not True: raise PermissionError('Confirmation required')
        intent=next((item for item in session['intents'].values()
                     if item['confirmation']['request_reference']==body['request_reference']),None)
        if not intent or type(body['csrf_token']) is not str or len(body['csrf_token'])!=64 or not body['csrf_token'].isascii() or not hmac.compare_digest(intent['csrf'],body['csrf_token']):
            raise PermissionError('Confirmation CSRF required')
        if intent['used'] or intent['expires']<=time.monotonic():
            return Gateway._error(409,'confirmation_expired_or_used')
        expected=intent['confirmation']
        if (type(body['expected_revision']) is not int or body['expected_revision']!=expected['expected_revision']
                or body['idempotency_key']!=expected['idempotency_key']):
            return Gateway._error(409,'revision_or_idempotency_conflict')
        intent['used']=True  # Consume before dispatch, including uncertain outcomes.
        eligibility=self.eligibility_for(intent['raw'])
        if not eligibility['eligible']:return self.eligibility_denial(eligibility)
        code,response=self.call(intent['raw'])  # Freshness, policy and CAS rechecked by gateway.
        if code!=200:return Gateway._error(code,'synthetic_action_rejected')
        return 200,dict(schema_version=1,state='inactive',operational_authorized=False,result=response['result'])


class _UIHandler(_Handler):
    def _reply(self,code,value):
        self.send_ui(code,canonical_bytes(value),'application/json; charset=utf-8')

    def send_ui(self,code,raw,content_type,cookie=None):
        self.close_connection=True
        if len(raw)>65536:return self._error(503,'service_unavailable')
        try:
            self.send_response(code)
            for name,value in SECURITY_HEADERS.items():
                if name=='Content-Type':value=content_type
                if name=='Content-Security-Policy':value=CSP
                self.send_header(name,value)
            self.send_header('Pragma','no-cache')
            self.send_header('Permissions-Policy','camera=(), microphone=(), geolocation=(), payment=(), usb=()')
            self.send_header('Cross-Origin-Resource-Policy','same-origin')
            if cookie:self.send_header('Set-Cookie',f'{COOKIE}={cookie}; HttpOnly; SameSite=Strict; Path={ROOT}; Max-Age={self.server.session_seconds}')
            self.send_header('Content-Length',str(len(raw)));self.end_headers()
            if self.command!='HEAD':self.wfile.write(raw)
        except (OSError,TimeoutError):pass

    def _dispatch(self):
        try:
            return self.dispatch_ui()
        except RateExceeded:return self._error(429,'rate_limited')
        except PermissionError:return self._error(403,'denied')
        except (TimeoutError,OSError):return self._error(408,'interrupted')
        except (ValueError,TypeError,KeyError,RecursionError,UnicodeError):return self._error(400,'invalid_request')
        except Exception:return self._error(503,'service_unavailable')

    def dispatch_ui(self):
        if sum(len(k)+len(v)+4 for k,v in self.headers.items())>8192:return self._error(431,'headers_too_large')
        if any(len(self.headers.get_all(name))!=1 for name in self.headers):return self._error(400,'duplicate_headers')
        origin=f'http://127.0.0.1:{self.server.server_address[1]}'
        if self.headers.get('Host')!=origin[7:]:return self._error(400,'host_binding_required')
        if any(name.lower() in ('authorization','forwarded','x-forwarded-for','x-forwarded-host','x-forwarded-proto','x-remote-user','x-synthetic-identity') for name in self.headers):
            return self._error(403,'untrusted_headers')
        site=self.headers.get('Sec-Fetch-Site','same-origin')
        navigation=self.command=='GET' and self.path==ROOT and site=='none'
        if ('Origin' in self.headers and self.headers['Origin']!=origin) or (site!='same-origin' and not navigation):
            return self._error(403,'same_origin_required')
        if self.command not in ('GET','POST'):return self._error(405,'method_unavailable')
        if len(self.path)>256 or any(c in self.path for c in ('?','#','%','\\')):return self._error(400,'invalid_route')
        if any(name in self.headers for name in ('Transfer-Encoding','Content-Encoding','Expect')):return self._error(400,'encoding_unavailable')
        if self.command=='GET':
            if self.headers.get('Content-Length','0')!='0':return self._error(400,'body_unavailable')
            if self.path in ASSETS:
                cookie=None
                if self.path==ROOT:cookie,_=self.server.open_session(self.headers.get('Cookie'))
                else:self.server.session(self.headers.get('Cookie'))
                filename,content_type=ASSETS[self.path]
                return self.send_ui(200,(ASSET_ROOT/filename).read_bytes(),content_type,cookie)
            if self.path==ROOT+'/api/overview':
                session=self.server.session(self.headers.get('Cookie'))
                return self._reply(200,self.server.overview(session))
            return self._error(404,'route_unavailable')
        if self.path not in (ROOT+'/api/prepare',ROOT+'/api/confirm'):return self._error(404,'route_unavailable')
        if self.headers.get('Origin')!=origin:return self._error(403,'same_origin_required')
        session=self.server.session(self.headers.get('Cookie'))
        if self.headers.get('Content-Type','').lower() not in ('application/json','application/json; charset=utf-8'):
            return self._error(415,'json_utf8_required')
        length=self.headers.get('Content-Length','')
        if not length or not length.isascii() or not length.isdecimal():return self._error(411,'length_required')
        if len(length)>6 or int(length)>MAX_REQUEST_BYTES:return self._error(413,'body_too_large')
        raw=self.rfile.read(int(length))
        if self.input_timed_out.is_set():return self._error(408,'interrupted')
        if len(raw)!=int(length):return self._error(400,'incomplete_body')
        body=strict_json_loads(raw.decode('utf-8'))
        if type(body) is not dict:raise ValueError('Exact object required')
        code,value=(self.server.prepare(session,body) if self.path.endswith('/prepare') else self.server.confirm(session,body))
        return self._reply(code,value)

    do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = do_HEAD = do_TRACE = do_CONNECT = _dispatch
