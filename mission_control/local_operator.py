"""Explicit local synthetic operator. No PID signalling, domain rules, or credentials on disk.

The same-user account and checkout are trusted. Kernel Unix peer credentials bind
control messages to a live process; an inert PID record is never sufficient.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import select
import signal
import socket
import stat
import struct
import subprocess
import sys
import time

from .command_center_ui import ROOT, CSP
from .connection_contracts import COMMAND_STAGES, CONNECTORS, validate_command_center
from .json_io import strict_json_loads
from .local_http import SECURITY_HEADERS

LABEL = 'LOCAL · SYNTHETIC · NOT PRODUCTION · NO ORGANIZATIONAL AUTHORIZATION'
STATE = 'state.json'
CONTROL = 'control.sock'
MAX_CONTROL = 4096
START_TIMEOUT = 90
STOP_TIMEOUT = 45
_CHILDREN = {}


class OperatorError(Exception):
    """Only constant, sanitized messages may reach the terminal."""


def identity(info):
    return info.st_dev,info.st_ino


def private_directory(info):
    if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.geteuid() or stat.S_IMODE(info.st_mode)!=0o700:
        raise OperatorError('Unsafe operator directory permissions')


def checked_path(path):
    path=Path(path)
    if not path.is_absolute() or '..' in path.parts or len(str(path).encode())>80:
        raise OperatorError('Unsafe operator directory')
    repository=Path(__file__).resolve().parents[1]
    if path==repository or repository in path.parents:
        raise OperatorError('Runtime state inside repository refused')
    return path


def walk_directory(path,create=False):
    """Open each component relative to its pinned parent, never following links.

    Platform ancestors provide namespace only, not application authority. Record
    their inode identities to detect substitution; ownership is required solely
    for the private application boundary, even for effective UID zero.
    """
    path=checked_path(path)
    descriptor=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    chain=[identity(os.fstat(descriptor))]
    try:
        for index,name in enumerate(path.parts[1:]):
            if create and index==len(path.parts)-2:
                try:os.mkdir(name,mode=0o700,dir_fd=descriptor)
                except FileExistsError:pass
            child=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=descriptor)
            os.close(descriptor);descriptor=child
            chain.append(identity(os.fstat(descriptor)))
        private_directory(os.fstat(descriptor))
        return descriptor,tuple(chain)
    except OSError:
        os.close(descriptor)
        raise OperatorError('Unverifiable operator directory') from None
    except BaseException:
        os.close(descriptor)
        raise


class RuntimeDirectory:
    """A verified directory handle; all controlled file operations are relative."""
    def __init__(self,path,descriptor,chain):
        self.path,self.fd,self.chain=Path(path),descriptor,chain
    def __str__(self):return str(self.path)
    def __truediv__(self,name):return self.path/name
    def verify(self):
        descriptor,chain=walk_directory(self.path)
        try:
            private_directory(os.fstat(self.fd))
            if chain!=self.chain or identity(os.fstat(descriptor))!=identity(os.fstat(self.fd)):
                raise OperatorError('Operator ancestor or directory changed')
        finally:os.close(descriptor)
    def iterdir(self):
        self.verify()
        return iter(self.path/name for name in os.listdir(self.fd))
    def exists(self,name):
        self.verify()
        try:os.stat(name,dir_fd=self.fd,follow_symlinks=False);return True
        except FileNotFoundError:return False
    def unlink(self,name):os.unlink(name,dir_fd=self.fd)
    def socket_path(self):
        self.verify()
        # Linux pins pathname lookup to the verified descriptor, including during
        # parent renames. Darwin has no equivalent descriptor path for AF_UNIX;
        # verify namespace before/after connect and require kernel peer identity.
        if sys.platform.startswith('linux'):return f'/proc/self/fd/{self.fd}/{CONTROL}'
        return str(self.path/CONTROL)


@contextmanager
def opened_directory(path,create=True):
    if isinstance(path,RuntimeDirectory):
        path.verify();yield path;return
    descriptor,chain=walk_directory(path,create=create)
    directory=RuntimeDirectory(path,descriptor,chain)
    try:
        directory.verify()
        yield directory
    finally:os.close(descriptor)


def safe_directory(path):
    with opened_directory(path) as directory:return directory.path


def default_directory():
    candidate=os.environ.get('XDG_RUNTIME_DIR')
    if candidate:
        # An environment variable is only a candidate. Never create or repair an
        # unverified base; reject invalid candidates instead of silently trusting.
        with opened_directory(candidate,create=False) as base:
            base.verify()
            return base.path/'mc-operator'
    return Path('/private/tmp' if sys.platform=='darwin' else '/tmp') / ('mc-local-operator-' + str(os.geteuid()))


def with_directory(function):
    from functools import wraps
    @wraps(function)
    def wrapped(directory,*args,**kwargs):
        with opened_directory(directory) as verified:
            return function(verified,*args,**kwargs)
    return wrapped


@with_directory
def safe_entry(directory,name,kind):
    directory.verify()
    info=os.stat(name,dir_fd=directory.fd,follow_symlinks=False)
    expected=stat.S_ISREG(info.st_mode) if kind=='file' else stat.S_ISSOCK(info.st_mode)
    if not expected or info.st_uid!=os.geteuid() or stat.S_IMODE(info.st_mode)!=0o600 or info.st_nlink!=1:
        raise OperatorError('Unsafe operator state')
    return info


@contextmanager
def locked(path):
    with opened_directory(path) as directory:
        # The stable directory inode is the lock: no removable lock/PID file.
        fcntl.flock(directory.fd,fcntl.LOCK_EX)
        directory.verify()  # Recheck after lock wait, before trusting contents.
        if set(os.listdir(directory.fd))- {STATE,CONTROL}:
            raise OperatorError('Unexpected operator state or lock file')
        yield directory


def peer(connection):
    if sys.platform.startswith('linux'):
        pid,uid,_=struct.unpack('3i',connection.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
    elif sys.platform=='darwin':
        # Darwin LOCAL_PEERPID and getpeereid, both kernel-derived.
        pid=struct.unpack('i',connection.getsockopt(0,2,4))[0]
        credentials=connection.getsockopt(0,1,80)  # LOCAL_PEERCRED / xucred
        version,uid=struct.unpack('II',credentials[:8])
        if version!=0: raise OperatorError('Unknown kernel peer credential version')
    else: raise OperatorError('Kernel peer identity unavailable on this platform')
    if uid!=os.geteuid() or pid<=1: raise OperatorError('Untrusted control process')
    return pid


def receive(connection):
    raw=b''
    while b'\n' not in raw:
        chunk=connection.recv(min(1024,MAX_CONTROL+1-len(raw)))
        if not chunk: raise OperatorError('Incomplete control response')
        raw+=chunk
        if len(raw)>MAX_CONTROL: raise OperatorError('Oversized control response')
    if raw.count(b'\n')!=1 or not raw.endswith(b'\n'): raise OperatorError('Malformed control response')
    return strict_json_loads(raw[:-1].decode('utf-8'))


def send(connection,value):
    connection.sendall(json.dumps(value,allow_nan=False,separators=(',',':')).encode()+b'\n')


def validate_state(value):
    fields={'version','pid','host','port','started_at','synthetic','instance','code_digest'}
    if type(value) is not dict or set(value)!=fields: raise OperatorError('Malformed operator state')
    if (type(value['version']) is not int or value['version']!=1 or type(value['pid']) is not int or value['pid']<=1
            or value['host']!='127.0.0.1' or type(value['port']) is not int or not 1<=value['port']<=65535
            or value['synthetic'] is not True or type(value['instance']) is not str
            or re.fullmatch('[0-9a-f]{32}',value['instance']) is None
            or type(value['code_digest']) is not str or re.fullmatch('[0-9a-f]{64}',value['code_digest']) is None
            or type(value['started_at']) is not str or re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+00:00',value['started_at']) is None):
        raise OperatorError('Malformed operator state')
    datetime.fromisoformat(value['started_at'])
    return value


def code_digest():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


@with_directory
def read_state(directory):
    before=safe_entry(directory,STATE,'file')
    descriptor=os.open(STATE,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory.fd)
    try:
        after=os.fstat(descriptor)
        if identity(before)!=identity(after) or not stat.S_ISREG(after.st_mode) or after.st_uid!=os.geteuid() or stat.S_IMODE(after.st_mode)!=0o600 or after.st_nlink!=1:
            raise OperatorError('Operator state changed')
        directory.verify()
    except BaseException:
        os.close(descriptor);raise
    with os.fdopen(descriptor,'rb') as file:
        data=file.read(MAX_CONTROL+1)
    if len(data)>MAX_CONTROL: raise OperatorError('Oversized operator state')
    return validate_state(strict_json_loads(data.decode('utf-8')))


@with_directory
def control(directory,command,state=None,timeout=5):
    before=safe_entry(directory,CONTROL,'socket')
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
        connection.settimeout(timeout);connection.connect(directory.socket_path())
        directory.verify()
        if identity(before)!=identity(safe_entry(directory,CONTROL,'socket')):raise OperatorError('Control socket changed')
        pid=peer(connection)
        if state is not None and (pid!=state['pid'] or state['code_digest']!=code_digest()):
            raise OperatorError('Managed process identity mismatch')
        send(connection,{'command':command})
        value=receive(connection)
        if state is not None and command=='status' and value!=state:
            raise OperatorError('Managed process state mismatch')
        return value


@with_directory
def status(directory):
    if not directory.exists(STATE):
        if directory.exists(CONTROL): raise OperatorError('Interrupted startup; state unverified')
        return None
    state=read_state(directory)
    control(directory,'status',state)
    return state


def response(connection,path,cookie=None):
    connection.request('GET',path,headers={'Cookie':cookie} if cookie else {})
    result=connection.getresponse()
    headers={}
    for name,value in result.getheaders():
        lower=name.lower()
        if lower in headers: raise OperatorError('Duplicate health response headers')
        headers[lower]=value
    if sum(len(k)+len(v)+4 for k,v in headers.items())>8192: raise OperatorError('Oversized health headers')
    data=result.read(65537)
    if result.status!=200 or len(data)>65536: raise OperatorError('Unexpected health response')
    for name,expected in SECURITY_HEADERS.items():
        if name in ('Content-Type','Content-Security-Policy'):continue
        if headers.get(name.lower())!=expected: raise OperatorError('Missing security header')
    if (headers.get('content-security-policy')!=CSP or headers.get('pragma')!='no-cache'
            or headers.get('cross-origin-resource-policy')!='same-origin'
            or headers.get('permissions-policy')!='camera=(), microphone=(), geolocation=(), payment=(), usb=()'
            or 'access-control-allow-origin' in headers or 'location' in headers):
        raise OperatorError('Unexpected security boundary')
    return headers,data


def verify_interface(state,timeout=4):
    validate_state(state)
    connection=http.client.HTTPConnection('127.0.0.1',state['port'],timeout=timeout)
    try:
        headers,data=response(connection,ROOT)
        if headers.get('content-type')!='text/html; charset=utf-8': raise OperatorError('Unexpected interface type')
        from .command_center_ui import ASSET_ROOT
        if data!=(ASSET_ROOT/'index.html').read_bytes(): raise OperatorError('Unexpected interface')
        cookie=headers.get('set-cookie','')
        if not re.fullmatch(r'mc_ceo_session=[0-9a-f]{64}; HttpOnly; SameSite=Strict; Path=/command-center; Max-Age=300',cookie):
            raise OperatorError('Unexpected synthetic session boundary')
        headers,data=response(connection,ROOT+'/api/overview',cookie.split(';')[0])
        if headers.get('content-type')!='application/json; charset=utf-8': raise OperatorError('Unexpected overview type')
        value=strict_json_loads(data.decode('utf-8'))
        expected={'schema_version','state','operational_authorized','queues','blocked_count','stages','items','readiness','counts','unavailable_fields','actions','csrf_token','connectors_disabled'}
        if (type(value) is not dict or set(value)!=expected or value['schema_version']!=1
                or value['state']!='inactive' or value['operational_authorized'] is not False
                or value['stages']!=list(COMMAND_STAGES) or value['connectors_disabled']!=7
                or value['actions']!=[] or value['readiness'] is not None):
            raise OperatorError('Unexpected synthetic overview')
        validate_command_center(dict(schema_revision=1,state='inactive',queues=value['queues']))
        if type(value['csrf_token']) is not str or not re.fullmatch('[0-9a-f]{64}',value['csrf_token']):
            raise OperatorError('Unexpected session response')
        if len(CONNECTORS)!=7 or any(item.enabled for item in CONNECTORS): raise OperatorError('Connector boundary failed')
    finally: connection.close()


@with_directory
def check(directory):
    state=status(directory)
    if state is None: raise OperatorError('Local operator is stopped')
    if control(directory,'health',state)!={'healthy':True,'synthetic':True,'operational_authorized':False}:
        raise OperatorError('Gateway health failed')
    verify_interface(state)
    return state


@with_directory
def start(directory,*,synthetic_development=False,host='127.0.0.1',port=0):
    if synthetic_development is not True: raise OperatorError('Explicit synthetic-development flag required')
    if host!='127.0.0.1' or type(port) is not int or not 0<=port<=65535: raise OperatorError('Literal IPv4 loopback and valid port required')
    if any(directory.iterdir()): raise OperatorError('Already running or stale state; inspect before recovery')
    # No shell, inherited credentials, terminal output, or browser are used.
    from multiprocessing import Pipe
    parent,child=Pipe(duplex=True)
    environment={key:value for key,value in os.environ.items() if key in ('PATH','HOME','LANG','LC_ALL','PYTHONPATH','DOCKER_HOST','XDG_RUNTIME_DIR')}
    environment['PYTHONDONTWRITEBYTECODE']='1'
    # Independent open description: do not inherit the command's flock.
    runtime_fd=os.open('.',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=directory.fd)
    try:
        process=subprocess.Popen([sys.executable,'-B','-m','mission_control.local_operator','_worker',str(directory),str(port),str(child.fileno()),str(runtime_fd)],
        cwd=Path(__file__).resolve().parents[1],env=environment,pass_fds=(child.fileno(),runtime_fd),
        stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
    except BaseException:
        parent.close()
        raise
    finally:
        os.close(runtime_fd)
        child.close()
    try:
        if not parent.poll(START_TIMEOUT): raise OperatorError('Startup timeout; cleanup pending until worker exits')
        if parent.recv()!='ready': raise OperatorError('Synthetic startup failed and cleaned up')
        state=check(directory)
        parent.send('accepted')
        _CHILDREN[process.pid]=process
        return state
    except BaseException:
        parent.close()  # Worker fails closed unless startup was accepted.
        try: process.wait(timeout=STOP_TIMEOUT)
        except subprocess.TimeoutExpired: raise OperatorError('Startup cleanup unconfirmed; no process was signalled') from None
        raise
    finally:parent.close()


@contextmanager
def exit_watch(pid):
    """Pin the live kernel process; reused numeric PIDs cannot satisfy this watch."""
    if sys.platform.startswith('linux') and hasattr(os,'pidfd_open'):
        descriptor=os.pidfd_open(pid)
        poller=select.poll();poller.register(descriptor,select.POLLIN)
        try:yield lambda seconds:bool(poller.poll(int(seconds*1000)))
        finally:os.close(descriptor)
    elif sys.platform=='darwin':
        queue=select.kqueue()
        queue.control([select.kevent(pid,filter=select.KQ_FILTER_PROC,
            flags=select.KQ_EV_ADD|select.KQ_EV_ONESHOT,fflags=select.KQ_NOTE_EXIT)],0,0)
        try:yield lambda seconds:bool(queue.control(None,1,seconds))
        finally:queue.close()
    else:raise OperatorError('Kernel process exit verification unavailable')


@with_directory
def stop(directory):
    state=status(directory)
    if state is None:return
    # No kill(), process groups, or OS signals. Only the verified peer may stop
    # itself. Pin kernel identity before a second verified control connection.
    with exit_watch(state['pid']) as exited:
        result=control(directory,'stop',state,timeout=STOP_TIMEOUT)
        if result!={'stopped':True} or not exited(5): raise OperatorError('Graceful shutdown unconfirmed')
    # Reap when invoked by the original launcher (otherwise not our child).
    process=_CHILDREN.pop(state['pid'],None)
    if process is not None: process.wait(timeout=5)
    else:
        try:os.waitpid(state['pid'],os.WNOHANG)
        except ChildProcessError:pass
    if any(directory.iterdir()): raise OperatorError('Shutdown cleanup incomplete')


@with_directory
def open_browser(directory,enabled=False,opener=None):
    state=check(directory)
    if enabled:
        import webbrowser
        if not (opener or webbrowser.open)(url(state),new=2): raise OperatorError('Browser could not be opened')
    return state


def url(state):
    validate_state(state)
    return f'http://127.0.0.1:{state["port"]}{ROOT}'


@contextmanager
def runtime_tools():
    if sys.platform=='darwin':
        import shutil
        binaries=[shutil.which(name) for name in ('postgres','initdb','pg_ctl')]
        if not all(binaries) or len({str(Path(p).parent) for p in binaries})!=1:
            raise OperatorError('Installed PostgreSQL 17.11 tools required')
        for binary in binaries:
            result=subprocess.run([binary,'--version'],capture_output=True,timeout=5,check=True)
            if not re.search(rb'\b17\.11\b',result.stdout):raise OperatorError('Exact PostgreSQL 17.11 required')
        yield str(Path(binaries[0]).parent)
    elif sys.platform.startswith('linux'):
        from scripts.local_postgres_tests import disposable_tools
        with disposable_tools() as directory:yield directory
    else:raise OperatorError('Unsupported local operator platform')


def worker(path,port,descriptor,runtime_fd):
    """Own the disposable infrastructure and existing UI, then clean up before ack."""
    from multiprocessing.connection import Connection
    import secrets
    import threading
    from contextlib import ExitStack
    from .command_center_ui import LocalCEOInterface, UIConfig, fresh
    from .connection_gateway import LocalContext
    from .connection_services import PhaseOneServices
    from .local_http import SyntheticBinding
    from .synthetic_identity import canonical_bytes
    parent=Connection(descriptor)
    # Compare the inherited pinned directory to the complete current namespace.
    probe,chain=walk_directory(path)
    try:
        if identity(os.fstat(probe))!=identity(os.fstat(runtime_fd)):raise OperatorError('Startup directory substituted')
    finally:os.close(probe)
    directory=RuntimeDirectory(path,runtime_fd,chain)
    listener=None;server=None;thread=None;stop_connection=None
    ready=False
    termination=threading.Event()
    previous_handlers={number:signal.signal(number,lambda *_:termination.set())
                       for number in (signal.SIGTERM,signal.SIGINT)}
    try:
        with ExitStack() as stack:
            tools=stack.enter_context(runtime_tools())
            os.environ['PATH']=tools+os.pathsep+os.environ.get('PATH','')
            # Reuse approved synthetic fixture/bootstrap, never production data.
            from tests.pilot_pg_support import PilotFixture
            from tests.connection_support import gateway_fixture,envelope,encoded,context
            from tests.pilot_support import JOURNEY
            class Fixture(PilotFixture):pass
            Fixture.setUpClass();stack.callback(Fixture.tearDownClass)
            fixture=Fixture();fixture.setUp()
            if termination.is_set():raise OperatorError('Startup interrupted')
            gateway,_,_=gateway_fixture(fixture.authority,PhaseOneServices(fixture.store))
            ctx=context('data_writer')
            config=UIConfig(reads=(encoded(envelope('journey.read',JOURNEY,role='data_writer',revision=0)),))
            binding=SyntheticBinding(secrets.token_hex(32),ctx.session_reference,ctx.policy_revision)
            server=LocalCEOInterface(gateway,binding,config,synthetic_development=True,host='127.0.0.1',port=port)
            thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':0.02},daemon=True);thread.start()
            listener=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
            directory.verify()
            previous_umask=os.umask(0o177)
            try:listener.bind(directory.socket_path())
            finally:os.umask(previous_umask)
            safe_entry(directory,CONTROL,'socket');directory.verify();listener.listen(4);listener.settimeout(1)
            state=dict(version=1,pid=os.getpid(),host='127.0.0.1',port=server.server_address[1],
                started_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),synthetic=True,
                instance=secrets.token_hex(16),code_digest=code_digest())
            descriptor=os.open(STATE,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600,dir_fd=directory.fd)
            with os.fdopen(descriptor,'w') as file:json.dump(state,file)
            parent.send('ready');ready=True
            # Parent checks health over the control socket before accepting startup.
            accepted=False;deadline=time.monotonic()+START_TIMEOUT
            while True:
                if termination.is_set():break
                if time.monotonic()>deadline+510:break  # At most ten minutes, never a persistent service.
                if not accepted and parent.poll():
                    try:accepted=parent.recv()=='accepted'
                    except EOFError:break
                    if not accepted:break
                    parent.close()
                if not accepted and time.monotonic()>deadline:break
                try: connection,_=listener.accept()
                except socket.timeout:continue
                try:
                    connection.settimeout(4);peer(connection)
                    message=receive(connection)
                    if type(message) is not dict or set(message)!={'command'}: raise OperatorError('Invalid control request')
                    command=message['command']
                    if command=='status':send(connection,state)
                    elif command=='health':
                        raw=encoded(envelope('health',role='audit_reviewer',revision=1))
                        code,body=gateway.handle('GET','/health',raw,context('audit_reviewer'))
                        if code!=200 or body.get('result')!={'state':'inactive'} or body.get('operational_authorized') is not False:
                            raise OperatorError('Synthetic health failed')
                        send(connection,dict(healthy=True,synthetic=True,operational_authorized=False))
                    elif command=='stop':stop_connection=connection;break
                    else:raise OperatorError('Unsupported control command')
                except Exception:
                    try:send(connection,{'error':'control_unavailable'})
                    except OSError:pass
                finally:
                    if connection is not stop_connection:connection.close()
            server.shutdown();server.server_close();thread.join(timeout=8)
            if thread.is_alive(): raise OperatorError('Listener shutdown unconfirmed')
            server=None
        # ExitStack stopped PostgreSQL and removed container/tools before ack.
        listener.close();listener=None
        for name in (STATE,CONTROL):directory.unlink(name)
        if stop_connection is not None:send(stop_connection,{'stopped':True})
    except BaseException:
        if server is not None:
            server.shutdown();server.server_close()
        if listener is not None:listener.close()
        for name in (STATE,CONTROL):
            try:directory.unlink(name)
            except FileNotFoundError:pass
        if not ready:
            try:parent.send('failed')
            except (BrokenPipeError,OSError):pass
        raise
    finally:
        for number,handler in previous_handlers.items():signal.signal(number,handler)
        parent.close()
        os.close(runtime_fd)
        if stop_connection is not None:stop_connection.close()


def main(argv=None):
    import argparse
    class SafeParser(argparse.ArgumentParser):
        def error(self,_message):
            self.exit(2,'Operator arguments rejected. Use --help.\n')
    parser=SafeParser(description=LABEL)
    parser.add_argument('--state-dir',type=Path,default=None)
    sub=parser.add_subparsers(dest='command',required=True)
    launch=sub.add_parser('start');launch.add_argument('--synthetic-development',action='store_true',required=True)
    launch.add_argument('--host',default='127.0.0.1');launch.add_argument('--port',type=int,default=0)
    for name in ('status','check','stop'):sub.add_parser(name)
    opening=sub.add_parser('open');opening.add_argument('--browser',action='store_true',help='Explicitly request local browser opening')
    demo=sub.add_parser('demo');demo.add_argument('--synthetic-development',action='store_true',required=True)
    args=parser.parse_args(argv)
    try:
        with locked(args.state_dir if args.state_dir is not None else default_directory()) as directory:
            if args.command=='start':state=start(directory,synthetic_development=args.synthetic_development,host=args.host,port=args.port)
            elif args.command=='status':state=status(directory)
            elif args.command=='check':state=check(directory)
            elif args.command=='open':state=open_browser(directory,args.browser)
            elif args.command=='stop':stop(directory);state=None
            else:
                try:
                    state=start(directory,synthetic_development=args.synthetic_development)
                    check(directory);open_browser(directory,False)
                finally:stop(directory)
                state=None
        print(LABEL)
        if state:
            print(f'PID {state["pid"]} | started {state["started_at"]} | synthetic=True')
            print(url(state))
        else:print('Stopped; no managed transient state remains.')
        return 0
    except (Exception,KeyboardInterrupt):
        print('Operator request failed closed. Inspect the runbook; no unverified process was signalled.',file=sys.stderr)
        return 1


if __name__=='__main__':
    if len(sys.argv)==6 and sys.argv[1]=='_worker':
        try:worker(Path(sys.argv[2]),int(sys.argv[3]),int(sys.argv[4]),int(sys.argv[5]))
        except BaseException:raise SystemExit(1)
    else:raise SystemExit(main())
