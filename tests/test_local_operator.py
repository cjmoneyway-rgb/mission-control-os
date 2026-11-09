"""Offline operator security/transport checks. No external services or PID signals."""
from contextlib import contextmanager
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import Mock,patch

from mission_control import local_operator as op
from mission_control.command_center_ui import CSP
from mission_control.local_http import SECURITY_HEADERS
from tests.command_center_support import running_ui


class LocalOperatorTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='op-test-',dir='/tmp')
        self.directory=Path(self.temp.name)
        self.state=dict(version=1,pid=os.getpid(),host='127.0.0.1',port=45678,
            started_at='2026-10-17T00:00:00+00:00',synthetic=True,instance='a'*32,code_digest=op.code_digest())
    def tearDown(self):self.temp.cleanup()
    def write(self,value=None):
        path=self.directory/op.STATE
        path.write_text(json.dumps(self.state if value is None else value));path.chmod(0o600)
        return path
    def test_disabled_start(self):
        with self.assertRaises(op.OperatorError):op.start(self.directory)
    def test_literal_binding_only(self):
        for host in ('0.0.0.0','localhost','127.0.0.2','::1','192.168.1.2','8.8.8.8','127.0.0.1:80','*','forwarded','https://127.0.0.1'):
            with self.subTest(host=host),self.assertRaises(op.OperatorError):op.start(self.directory,synthetic_development=True,host=host)
    def test_port_validation(self):
        for port in (-1,65536,True,'0',None):
            with self.subTest(port=port),self.assertRaises(op.OperatorError):op.start(self.directory,synthetic_development=True,port=port)
    def test_no_import_listener(self):
        import importlib
        with patch('socket.socket',side_effect=AssertionError('listener')):importlib.reload(op)
    def test_stopped_status(self):self.assertIsNone(op.status(self.directory))
    def test_stopped_stop(self):op.stop(self.directory)
    def test_stopped_check(self):
        with self.assertRaises(op.OperatorError):op.check(self.directory)
    def test_stale_pid(self):
        self.write()
        with self.assertRaises(FileNotFoundError):op.status(self.directory)
    def test_pid_mismatch(self):
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as server:
            server.bind(str(self.directory/op.CONTROL));(self.directory/op.CONTROL).chmod(0o600);server.listen(1)
            with self.assertRaises(op.OperatorError):op.control(self.directory,'status',dict(self.state,pid=os.getpid()+123))
    def test_unrelated_process_stop_refused(self):
        self.write(dict(self.state,pid=1))
        with patch.object(op,'control') as control,self.assertRaises(op.OperatorError):op.stop(self.directory)
        control.assert_not_called()
    def test_malformed_state(self):
        for value in ({},dict(self.state,role='ceo'),dict(self.state,synthetic=False),dict(self.state,host='localhost'),dict(self.state,port=True),dict(self.state,pid='123'),dict(self.state,started_at='\x1b[31m')):
            self.write(value)
            with self.subTest(value=value),self.assertRaises((op.OperatorError,ValueError)):op.read_state(self.directory)
    def test_duplicate_keys(self):
        self.write().write_text('{"pid":1,"pid":2}')
        with self.assertRaises(ValueError):op.read_state(self.directory)
    def test_nonfinite_state(self):
        self.write().write_text('{"pid":NaN}')
        with self.assertRaises(ValueError):op.read_state(self.directory)
    def test_invalid_utf8_state(self):
        self.write().write_bytes(b'\xff')
        with self.assertRaises(UnicodeError):op.read_state(self.directory)
    def test_oversized_state(self):
        self.write().write_bytes(b' '*5000)
        with self.assertRaises(op.OperatorError):op.read_state(self.directory)
    def test_symlink_state(self):
        (self.directory/op.STATE).symlink_to('/dev/null')
        with self.assertRaises(op.OperatorError):op.read_state(self.directory)
    def test_symlink_lock(self):
        (self.directory/'lock').symlink_to('/dev/null')
        with self.assertRaises(op.OperatorError):
            with op.locked(self.directory):pass
    def test_symlink_socket(self):
        (self.directory/op.CONTROL).symlink_to('/dev/null')
        with self.assertRaises(op.OperatorError):op.control(self.directory,'status')
    def test_symlink_directory(self):
        link=self.directory/'link';link.symlink_to(self.directory,target_is_directory=True)
        with self.assertRaises(op.OperatorError):op.safe_directory(link)
    def test_unsafe_state_permissions(self):
        self.write().chmod(0o644)
        with self.assertRaises(op.OperatorError):op.read_state(self.directory)
    def test_unsafe_directory_permissions(self):
        self.directory.chmod(0o755)
        with self.assertRaises(op.OperatorError):op.safe_directory(self.directory)
    def test_hardlinked_state(self):
        os.link(self.write(),self.directory/'other')
        with self.assertRaises(op.OperatorError):op.read_state(self.directory)
    def test_traversal_directory(self):
        with self.assertRaises(op.OperatorError):op.safe_directory(self.directory/'..'/'other')
    def test_double_start(self):
        self.write()
        with patch('subprocess.Popen') as process,self.assertRaises(op.OperatorError):op.start(self.directory,synthetic_development=True)
        process.assert_not_called()
    def test_open_disabled(self):
        opener=Mock()
        with patch.object(op,'check',return_value=self.state):self.assertEqual(op.open_browser(self.directory,False,opener),self.state)
        opener.assert_not_called()
    def test_explicit_browser_open(self):
        opener=Mock(return_value=True)
        with patch.object(op,'check',return_value=self.state):op.open_browser(self.directory,True,opener)
        opener.assert_called_once_with('http://127.0.0.1:45678/command-center',new=2)
    def test_no_open_when_unhealthy(self):
        opener=Mock()
        with patch.object(op,'check',side_effect=op.OperatorError('health')),self.assertRaises(op.OperatorError):op.open_browser(self.directory,True,opener)
        opener.assert_not_called()
    def test_sanitized_terminal(self):
        output=io.StringIO()
        with patch.object(op,'status',side_effect=RuntimeError('SECRET directive csrf=secret')),patch('sys.stderr',output):self.assertEqual(op.main(['--state-dir',str(self.directory),'status']),1)
        self.assertNotIn('SECRET',output.getvalue());self.assertNotIn('csrf',output.getvalue())
    def test_graceful_timeout_no_signals(self):
        @contextmanager
        def watch(_):yield lambda _:False
        with patch.object(op,'status',return_value=self.state),patch.object(op,'exit_watch',watch),patch.object(op,'control',side_effect=TimeoutError),patch('os.kill') as kill,self.assertRaises(TimeoutError):op.stop(self.directory)
        kill.assert_not_called()
    def test_exit_not_confirmed(self):
        @contextmanager
        def watch(_):yield lambda _:False
        with patch.object(op,'status',return_value=self.state),patch.object(op,'exit_watch',watch),patch.object(op,'control',return_value={'stopped':True}),self.assertRaises(op.OperatorError):op.stop(self.directory)
    def test_health_rejects_identity(self):
        with patch.object(op,'status',return_value=self.state),patch.object(op,'control',return_value={'healthy':True,'synthetic':False,'operational_authorized':False}),self.assertRaises(op.OperatorError):op.check(self.directory)
    def test_control_strict_framing(self):
        for raw in (b'{}\n{}\n',b'{}\nx',b'\xff\n',b'{"a":1,"a":2}\n',b' '*4097):
            with mock_socket(raw) as connection:
                with self.assertRaises((op.OperatorError,ValueError,UnicodeError)):op.receive(connection)
    def test_control_peer_uid(self):
        connection=Mock();connection.getsockopt.return_value=__import__('struct').pack('3i',os.getpid(),os.getuid()+1,0)
        with patch.object(op.sys,'platform','linux'),self.assertRaises(op.OperatorError):op.peer(connection)
    def test_no_pid_signal_implementation(self):
        text=Path(op.__file__).read_text()
        self.assertNotIn('os.kill(',text);self.assertNotIn('shell=True',text)
    def test_live_interface_verification(self):
        with running_ui() as (server,_):op.verify_interface(dict(self.state,port=server.server_address[1]))
    def test_health_transport_failures(self):
        base={name.lower():value for name,value in SECURITY_HEADERS.items()}
        base.update({'content-security-policy':CSP,'pragma':'no-cache','cross-origin-resource-policy':'same-origin','permissions-policy':'camera=(), microphone=(), geolocation=(), payment=(), usb=()'})
        for code,changes in ((302,{'location':'https://example.invalid'}),(200,{'x-frame-options':None}),(200,{'access-control-allow-origin':'*'}),(200,{'content-security-policy':'default-src *'})):
            headers={**base,**changes};headers={k:v for k,v in headers.items() if v is not None}
            result=Mock(status=code);result.getheaders.return_value=list(headers.items());result.read.return_value=b'{}'
            connection=Mock();connection.getresponse.return_value=result
            with self.subTest(code=code,changes=changes),self.assertRaises(op.OperatorError):op.response(connection,'/command-center')
    def test_health_timeout(self):
        with patch.object(op.http.client,'HTTPConnection') as cls:
            cls.return_value.request.side_effect=TimeoutError
            with self.assertRaises(TimeoutError):op.verify_interface(self.state)
    def test_malformed_overview_and_types(self):
        from mission_control.command_center_ui import ASSET_ROOT
        root={'content-type':'text/html; charset=utf-8','set-cookie':'mc_ceo_session='+'a'*64+'; HttpOnly; SameSite=Strict; Path=/command-center; Max-Age=300'}
        for headers,data in (({'content-type':'text/plain'},b'{}'),({'content-type':'application/json; charset=utf-8'},b'{}'),({'content-type':'application/json; charset=utf-8'},b'{"x":NaN}')):
            with patch.object(op,'response',side_effect=[(root,(ASSET_ROOT/'index.html').read_bytes()),(headers,data)]),self.assertRaises((op.OperatorError,ValueError)):op.verify_interface(self.state)
    def test_seven_disabled_connectors(self):
        self.assertEqual(len(op.CONNECTORS),7);self.assertTrue(all(not item.enabled for item in op.CONNECTORS))

    def test_platform_managed_ancestor_is_namespace_only(self):
        real=os.fstat;leaf=self.directory.stat().st_ino
        def platform_owner(fd):
            info=real(fd)
            if info.st_ino==leaf:return info
            values=list(info);values[4]=os.geteuid()+123
            return os.stat_result(values)
        with patch.object(op.os,'fstat',side_effect=platform_owner),op.locked(self.directory) as directory:
            self.assertEqual(list(directory.iterdir()),[])
    def test_runtime_owner_must_match_effective_identity(self):
        with patch.object(op.os,'geteuid',return_value=os.geteuid()+123),self.assertRaises(op.OperatorError):op.safe_directory(self.directory)
    def test_root_does_not_bypass_private_permissions(self):
        self.directory.chmod(0o777)
        with patch.object(op.os,'geteuid',return_value=0),self.assertRaises(op.OperatorError):op.safe_directory(self.directory)
    def test_root_does_not_bypass_private_ownership(self):
        # UID zero still must match the leaf owner; no privileged exemption.
        info=list(self.directory.stat());info[4]=12345
        with patch.object(op.os,'geteuid',return_value=0),self.assertRaises(op.OperatorError):op.private_directory(os.stat_result(info))
    def test_xdg_private_existing_base_preferred(self):
        with patch.dict(os.environ,{'XDG_RUNTIME_DIR':str(self.directory)}):
            selected=op.default_directory()
            self.assertEqual(selected,self.directory/'mc-operator')
            self.assertFalse(selected.exists())
            with op.locked(selected) as directory:self.assertEqual(list(directory.iterdir()),[])
    def test_xdg_unsafe_environment_not_trusted(self):
        for candidate in ('/tmp','relative/path',str(self.directory/'missing')):
            with patch.dict(os.environ,{'XDG_RUNTIME_DIR':candidate}),self.assertRaises((op.OperatorError,OSError)):op.default_directory()
    def test_xdg_wrong_owner_rejected(self):
        with patch.dict(os.environ,{'XDG_RUNTIME_DIR':str(self.directory)}),patch.object(op.os,'geteuid',return_value=os.geteuid()+1),self.assertRaises(op.OperatorError):op.default_directory()
    def test_xdg_symlink_rejected(self):
        link=self.directory/'xdg';link.symlink_to(self.directory,target_is_directory=True)
        with patch.dict(os.environ,{'XDG_RUNTIME_DIR':str(link)}),self.assertRaises(op.OperatorError):op.default_directory()
    def test_repository_runtime_refused(self):
        repository=Path(op.__file__).resolve().parents[1]
        with self.assertRaises(op.OperatorError):op.safe_directory(repository/'runtime')
        self.assertFalse((repository/'runtime').exists())
    def test_ancestor_symlink_refused(self):
        actual=self.directory/'real';actual.mkdir(mode=0o700)
        link=self.directory/'parent';link.symlink_to(actual,target_is_directory=True)
        with self.assertRaises(op.OperatorError):op.safe_directory(link/'runtime')
        self.assertFalse((actual/'runtime').exists())
    def test_ancestor_substitution_after_open_rejected(self):
        parent=self.directory/'parent';parent.mkdir(mode=0o700)
        leaf=parent/'runtime'
        with op.opened_directory(leaf) as directory:
            moved=self.directory/'moved';parent.rename(moved)
            parent.mkdir(mode=0o700);leaf.mkdir(mode=0o700)
            with self.assertRaises(op.OperatorError):directory.verify()
            with self.assertRaises(op.OperatorError):op.status(directory)
            self.assertEqual(list(leaf.iterdir()),[])
    def test_directory_substitution_during_lock_wait_rejected(self):
        real=op.fcntl.flock
        def replace(fd,mode):
            real(fd,mode)
            self.directory.rename(self.directory.with_name(self.directory.name+'-old'))
            self.directory.mkdir(mode=0o700)
        moved=self.directory.with_name(self.directory.name+'-old')
        try:
            with patch.object(op.fcntl,'flock',side_effect=replace),self.assertRaises(op.OperatorError):
                with op.locked(self.directory):pass
        finally:moved.rmdir()
    def test_state_substitution_between_stat_and_open_rejected(self):
        path=self.write();original=op.safe_entry
        def substitute(directory,name,kind):
            before=original(directory,name,kind)
            replacement=self.directory/'replacement';replacement.write_text(path.read_text());replacement.chmod(0o600)
            replacement.replace(path)
            return before
        with patch.object(op,'safe_entry',side_effect=substitute),self.assertRaises(op.OperatorError):op.read_state(self.directory)
    def test_unexpected_pid_or_lock_file_rejected(self):
        for name in ('operator.pid','lock'):
            path=self.directory/name;path.write_text('1');path.chmod(0o600)
            with self.assertRaises(op.OperatorError):
                with op.locked(self.directory):pass
            path.unlink()
    def test_state_fifo_rejected_without_blocking(self):
        os.mkfifo(self.directory/op.STATE,0o600)
        with self.assertRaises(op.OperatorError):op.read_state(self.directory)

    def test_boolean_schema_version_rejected(self):
        with self.assertRaises(op.OperatorError):op.validate_state(dict(self.state,version=True))
    def test_process_creation_failure_closes_startup_pipes(self):
        from multiprocessing import Pipe
        parent,child=Pipe()
        with patch('multiprocessing.Pipe',return_value=(parent,child)),patch('subprocess.Popen',side_effect=OSError('synthetic spawn failure')):
            with self.assertRaises(OSError):op.start(self.directory,synthetic_development=True)
        self.assertTrue(parent.closed);self.assertTrue(child.closed)
        self.assertEqual(list(self.directory.iterdir()),[])

    def test_parser_errors_never_echo_rejected_values(self):
        for arguments in (['start','--synthetic-development','--port','synthetic-rejected-marker'],['--unknown','synthetic-rejected-marker']):
            output=io.StringIO()
            with patch('sys.stderr',output),self.assertRaises(SystemExit) as stopped:
                op.main(arguments)
            self.assertEqual(stopped.exception.code,2)
            self.assertEqual(output.getvalue(),'Operator arguments rejected. Use --help.\n')
            self.assertEqual(list(self.directory.iterdir()),[])


@contextmanager
def mock_socket(raw):
    connection=Mock();connection.recv.side_effect=[raw,b'']
    yield connection
