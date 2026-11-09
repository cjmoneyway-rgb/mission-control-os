"""Real disposable PostgreSQL/operator subprocess lifecycle verification."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from mission_control import local_operator as op


class OperatorPostgreSQLTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='operator-pg-',dir='/tmp')
        self.directory=Path(self.temp.name)
    def tearDown(self):
        with op.locked(self.directory):
            if (self.directory/op.STATE).exists():op.stop(self.directory)
        self.assertEqual(list(self.directory.iterdir()),[])
        self.temp.cleanup()
    def test_start_status_health_open_stop_cleanup(self):
        with op.locked(self.directory):
            state=op.start(self.directory,synthetic_development=True)
            self.assertGreater(state['port'],0);self.assertEqual(state['host'],'127.0.0.1')
            self.assertEqual(op.status(self.directory),state)
            self.assertEqual(op.check(self.directory),state)
            self.assertEqual(op.open_browser(self.directory,False),state)
            self.assertEqual((self.directory/op.STATE).stat().st_mode&0o777,0o600)
            self.assertEqual((self.directory/op.CONTROL).stat().st_mode&0o777,0o600)
            op.stop(self.directory)
            with socket.socket() as probe:self.assertNotEqual(probe.connect_ex(('127.0.0.1',state['port'])),0)
    def test_concurrent_start_and_double_start(self):
        def start():
            try:
                with op.locked(self.directory):return op.start(self.directory,synthetic_development=True)
            except op.OperatorError:return None
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:start(),range(2)))
        self.assertEqual(sum(value is not None for value in results),1)
        with op.locked(self.directory),self.assertRaises(op.OperatorError):op.start(self.directory,synthetic_development=True)
    def test_concurrent_stop(self):
        with op.locked(self.directory):op.start(self.directory,synthetic_development=True)
        def stop(_):
            with op.locked(self.directory):op.stop(self.directory)
        with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(stop,range(2)))
        self.assertIsNone(op.status(self.directory))
    def test_occupied_port_cleanup(self):
        with socket.socket() as occupied:
            occupied.bind(('127.0.0.1',0));occupied.listen(1)
            with op.locked(self.directory),self.assertRaises(op.OperatorError):op.start(self.directory,synthetic_development=True,port=occupied.getsockname()[1])
        self.assertEqual(list(self.directory.iterdir()),[])
    def test_failed_health_startup_cleanup(self):
        with op.locked(self.directory),patch.object(op,'verify_interface',side_effect=op.OperatorError('rejected')),self.assertRaises(op.OperatorError):op.start(self.directory,synthetic_development=True)
        self.assertEqual(list(self.directory.iterdir()),[])
    def test_interrupted_startup_cleanup(self):
        with op.locked(self.directory),patch.object(op,'check',side_effect=KeyboardInterrupt),self.assertRaises(KeyboardInterrupt):op.start(self.directory,synthetic_development=True)
        self.assertEqual(list(self.directory.iterdir()),[])
    def test_demo_command_and_no_leakage(self):
        result=subprocess.run([sys.executable,'-B','-m','mission_control.local_operator','--state-dir',str(self.directory),'demo','--synthetic-development'],capture_output=True,timeout=120)
        self.assertEqual(result.returncode,0,result.stderr.decode())
        self.assertIn(b'NO ORGANIZATIONAL AUTHORIZATION',result.stdout)
        for marker in (b'csrf',b'mc_ceo_session',b'Bearer',b'syn-pilot',b'Traceback',b'password'):
            self.assertNotIn(marker,result.stdout+result.stderr)
        self.assertEqual(list(self.directory.iterdir()),[])
    def test_failed_demo_after_verified_start_cleans_up(self):
        import io
        real_check=op.check;verified=[]
        def fail_second_check(directory):
            if verified:raise op.OperatorError('Synthetic interrupted demonstration')
            state=real_check(directory);verified.append(state);return state
        output=io.StringIO()
        with patch.object(op,'check',side_effect=fail_second_check),patch('sys.stderr',output),patch('sys.stdout',output):
            code=op.main(['--state-dir',str(self.directory),'demo','--synthetic-development'])
        self.assertEqual(code,1);self.assertEqual(len(verified),1)
        self.assertEqual(list(self.directory.iterdir()),[])
        self.assertFalse(op._CHILDREN)
        with socket.socket() as probe:self.assertNotEqual(probe.connect_ex(('127.0.0.1',verified[0]['port'])),0)
        for forbidden in ('syn-pilot','csrf','mc_ceo_session','Bearer','Traceback'):
            self.assertNotIn(forbidden,output.getvalue())
    def test_state_tamper_and_pid_reuse_refused(self):
        import json
        with op.locked(self.directory):
            state=op.start(self.directory,synthetic_development=True)
            path=self.directory/op.STATE
            path.write_text(json.dumps(dict(state,pid=os.getpid())))
            try:
                with self.assertRaises(op.OperatorError):op.stop(self.directory)
                with self.assertRaises(op.OperatorError):op.status(self.directory)
            finally:path.write_text(json.dumps(state))
            self.assertEqual(op.check(self.directory),state)
    def test_port_race_uses_actual_listener(self):
        # Two separate managed instances ask the kernel for port zero; neither
        # preselects/free-checks a port. Both listeners must remain distinct.
        with tempfile.TemporaryDirectory(prefix='operator-other-',dir='/tmp') as second:
            second=Path(second)
            try:
                with op.locked(self.directory):first=op.start(self.directory,synthetic_development=True)
                with op.locked(second):other=op.start(second,synthetic_development=True)
                self.assertNotEqual(first['port'],other['port'])
                op.check(self.directory);op.check(second)
            finally:
                with op.locked(second):op.stop(second)
                self.assertEqual(list(second.iterdir()),[])

    def test_governed_worker_termination_cleans_owned_resources(self):
        import signal
        with op.locked(self.directory):
            state=op.start(self.directory,synthetic_development=True)
            # Pin this owned worker and reverify the peer before injecting failure.
            descriptor=os.pidfd_open(state['pid'])
            try:
                self.assertEqual(op.status(self.directory),state)
                signal.pidfd_send_signal(descriptor,signal.SIGTERM)
                process=op._CHILDREN.pop(state['pid']);self.assertEqual(process.wait(timeout=45),0)
            finally:os.close(descriptor)
            self.assertIsNone(op.status(self.directory))
            self.assertEqual(list(self.directory.iterdir()),[])
            with socket.socket() as probe:self.assertNotEqual(probe.connect_ex(('127.0.0.1',state['port'])),0)
