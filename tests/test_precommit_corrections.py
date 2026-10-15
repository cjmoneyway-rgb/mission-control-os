"""Regression tests for the Phase 1A review findings; synthetic fixtures only."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import io
import json
import multiprocessing
import os
from pathlib import Path
import tempfile
import threading
import types
import unittest
from unittest.mock import patch

import main
from mission_control import MissionControlOS
from mission_control.audit import JsonlAuditLog
from mission_control.config import load_departments
from mission_control.contracts import Approval, RegistryRecord, digest
from mission_control.engine import BlockedExecution
from mission_control.json_io import strict_json_loads
from mission_control.providers import MockProvider, OpenAIProvider, SafetyDecision
from tests.hardening_support import SyntheticAuthority, synthetic_clearance
from tests.test_openai_provider import FakeOpenAI


def _append_worker(path, connection):
    try:
        record = MissionControlOS(audit_log=None).run('synthetic')
        connection.send('ready')
        connection.recv()
        connection.send('attempting')
        JsonlAuditLog(path).append(record)
        connection.send(record.execution_id)
    finally:
        connection.close()


def _interrupted_retention_worker(path, connection):
    def pause_before_replace(*args):
        connection.send('prepared')
        connection.recv()
    with patch('mission_control.audit.os.replace', side_effect=pause_before_replace):
        JsonlAuditLog(path, retention_days=1).purge_expired()


class PrecommitCorrectionsTests(unittest.TestCase):
    def _audit_fixture(self, folder):
        path = Path(folder) / 'audit.jsonl'
        log = JsonlAuditLog(path, retention_days=1)
        record = MissionControlOS(audit_log=None).run('synthetic')
        log.append(replace(record, created_at='2000-01-01T00:00:00+00:00'))
        log.append(record)
        return log, record

    @unittest.skipUnless(os.name == 'posix', 'flock requires POSIX')
    def test_concurrent_process_append_and_retention(self):
        with tempfile.TemporaryDirectory() as folder:
            log, record = self._audit_fixture(folder)
            original = log.path.read_bytes()
            parent, child = multiprocessing.get_context('fork').Pipe()
            process = multiprocessing.get_context('fork').Process(target=_append_worker, args=(str(log.path), child))
            process.start()
            child.close()
            entered, release = threading.Event(), threading.Event()
            failures = []
            publish = log._publish_view
            def paused_publish(*args):
                entered.set()
                if not release.wait(5):
                    raise RuntimeError('test synchronization timeout')
                return publish(*args)
            def retain():
                try:
                    log.purge_expired()
                except BaseException as exc:
                    failures.append(exc)
            thread = threading.Thread(target=retain)
            try:
                self.assertTrue(parent.poll(5))
                self.assertEqual(parent.recv(), 'ready')
                with patch.object(log, '_publish_view', side_effect=paused_publish):
                    thread.start()
                    self.assertTrue(entered.wait(5))
                    parent.send('start')
                    self.assertTrue(parent.poll(5))
                    self.assertEqual(parent.recv(), 'attempting')
                    self.assertFalse(parent.poll(0.1))  # Append waits on retention lock.
                    release.set()
                    thread.join(5)
                    self.assertFalse(thread.is_alive())
                    self.assertEqual(failures, [])
                    self.assertTrue(parent.poll(5))
                    appended_id = parent.recv()
                process.join(5)
                self.assertEqual(process.exitcode, 0)
                source = log.path.read_bytes()
                self.assertTrue(source.startswith(original))
                rows = [strict_json_loads(line) for line in source.splitlines()]
                self.assertEqual(len(rows), 3)
                self.assertEqual(rows[-1]['execution_id'], appended_id)
                self.assertEqual(log.purge_expired()['retained_count'], 2)
                view = log.retained_path.read_bytes()
                self.assertEqual(view, b''.join(source.splitlines(keepends=True)[1:]))
                self.assertEqual(log.path.read_bytes(), source)
                self.assertEqual(log.retained_path.stat().st_mode & 0o777, 0o600)
            finally:
                release.set()
                if thread.ident is not None:
                    thread.join(5)
                if process.is_alive():
                    process.terminate()
                process.join(5)
                parent.close()

    def test_retention_failures_preserve_source_and_previous_view(self):
        for failure in (OSError('synthetic replace failure'), KeyboardInterrupt()):
            with self.subTest(failure=type(failure).__name__), tempfile.TemporaryDirectory() as folder:
                log, record = self._audit_fixture(folder)
                log.purge_expired()
                source, view = log.path.read_bytes(), log.retained_path.read_bytes()
                with patch('mission_control.audit.os.replace', side_effect=failure), self.assertRaises(type(failure)):
                    log.purge_expired()
                self.assertEqual(log.path.read_bytes(), source)
                self.assertEqual(log.retained_path.read_bytes(), view)
                self.assertEqual(list(Path(folder).glob('*.retention-*')), [])
                log.append(record)  # Failure released the lock.
                self.assertTrue(log.path.read_bytes().startswith(source))

    def test_retention_sync_failure_preserves_source(self):
        for fail_at in (1, 2):  # Before replace, or after complete atomic publication.
            with self.subTest(fail_at=fail_at), tempfile.TemporaryDirectory() as folder:
                log, _ = self._audit_fixture(folder)
                log.purge_expired()
                original, view = log.path.read_bytes(), log.retained_path.read_bytes()
                real_fsync = os.fsync
                calls = []
                def sync(fd):
                    calls.append(fd)
                    if len(calls) == fail_at:
                        raise OSError('synthetic sync failure')
                    return real_fsync(fd)
                with patch('mission_control.audit.os.fsync', side_effect=sync), self.assertRaises(OSError):
                    log.purge_expired()
                self.assertEqual(log.path.read_bytes(), original)
                self.assertEqual(log.retained_path.read_bytes(), view)

    @unittest.skipUnless(os.name == 'posix', 'process interruption requires POSIX')
    def test_process_interruption_preserves_records_and_releases_lock(self):
        with tempfile.TemporaryDirectory() as folder:
            log, record = self._audit_fixture(folder)
            log.purge_expired()
            source, view = log.path.read_bytes(), log.retained_path.read_bytes()
            parent, child = multiprocessing.get_context('fork').Pipe()
            process = multiprocessing.get_context('fork').Process(target=_interrupted_retention_worker, args=(str(log.path), child))
            process.start()
            child.close()
            try:
                self.assertTrue(parent.poll(5))
                self.assertEqual(parent.recv(), 'prepared')
                process.terminate()
                process.join(5)
                self.assertFalse(process.is_alive())
                self.assertEqual(log.path.read_bytes(), source)
                self.assertEqual(log.retained_path.read_bytes(), view)
                leftovers = list(Path(folder).glob('*.retention-*'))
                self.assertEqual(len(leftovers), 1)
                self.assertEqual(leftovers[0].stat().st_mode & 0o777, 0o600)
                log.append(record)
                self.assertTrue(log.path.read_bytes().startswith(source))
                log.purge_expired()  # Unique staging path safely ignores interrupted staging.
            finally:
                if process.is_alive():
                    process.terminate()
                process.join(5)
                parent.close()

    def test_retention_never_migrates_legacy_records(self):
        with tempfile.TemporaryDirectory() as folder:
            log, record = self._audit_fixture(folder)
            log.purge_expired()
            legacy = {'created_at': record.created_at, 'directive': 'synthetic legacy'}
            log.path.write_text(json.dumps(legacy) + '\n')
            source, view = log.path.read_bytes(), log.retained_path.read_bytes()
            with self.assertRaises(ValueError):
                log.purge_expired()
            self.assertEqual(log.path.read_bytes(), source)
            self.assertEqual(log.retained_path.read_bytes(), view)

    def test_duplicates_rejected_at_every_json_boundary(self):
        duplicates = ('{"x":1,"x":2}', '{"outer":{"x":1,"x":2}}')
        for raw in duplicates:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                strict_json_loads(raw)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'departments.json'
            path.write_text('{"departments":[],"departments":[]}')
            with self.assertRaises(ValueError):
                load_departments(path)
            path.write_text('{"departments":[{"id":"a","id":"b"}]}')
            with self.assertRaises(ValueError):
                load_departments(path)
            log, record = self._audit_fixture(folder)
            raw = log.path.read_text().replace('"schema_revision": 1', '"schema_revision": 1, "schema_revision": 1')
            log.path.write_text(raw)
            with self.assertRaises(ValueError):
                log.purge_expired()
            self.assertEqual(log.path.read_text(), raw)
        provider = object.__new__(OpenAIProvider)
        raw = '{"department_id":"invalid","department_id":"executive_strategy","rationale":"synthetic","confidence":0.5}'
        with patch.object(provider, '_respond', return_value=raw), self.assertRaises(RuntimeError):
            provider.classify('synthetic', load_departments())

    def _approved_record(self):
        record = RegistryRecord('record-1', 1, 'dept-1', 'title-1', 'owner-1', 'policy-1', 'active')
        approval = Approval('record-1', 1, digest(record.payload()), 'evidence-1')
        authority = SyntheticAuthority(approval, {('department','dept-1'), ('title','title-1'), ('owner','owner-1'), ('policy','policy-1')})
        return replace(record, approval=approval), authority

    def test_evidence_must_resolve_and_match(self):
        record, authority = self._approved_record()
        record.validate(authority)
        for resolved in (None, True, 'unresolved', replace(authority.evidence, authorized=False),
                         replace(authority.evidence, approval=replace(record.approval, evidence_reference='different')),
                         replace(authority.evidence, expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)),
                         replace(authority.evidence, valid_from=datetime.now(timezone.utc)+timedelta(days=1)),
                         replace(authority.evidence, expires_at=datetime.now())):
            with self.subTest(evidence=type(resolved).__name__), patch.object(authority, 'resolve_approval', return_value=resolved), self.assertRaises(ValueError):
                record.validate(authority)
        with patch.object(authority, 'resolve_approval', side_effect=OSError('synthetic')), self.assertRaises(ValueError):
            record.validate(authority)
        for unavailable in (None, lambda evidence: True, object()):
            with self.assertRaises(ValueError):
                record.validate(unavailable)
        with self.assertRaises(ValueError):
            replace(record, approval=replace(record.approval, evidence_reference='unresolved')).validate(authority)
        with self.assertRaises(ValueError):
            replace(record, revision=2).validate(authority)

    def test_all_registry_references_must_exist(self):
        record, authority = self._approved_record()
        for reference in tuple(authority.references):
            authority.references.remove(reference)
            with self.subTest(reference=reference), self.assertRaises(ValueError):
                record.validate(authority)
            authority.references.add(reference)
        with patch.object(authority, 'resolve_reference', side_effect=OSError('synthetic')), self.assertRaises(ValueError):
            record.validate(authority)

    def test_injected_provider_cannot_self_declare_offline(self):
        class Impostor:
            name = 'mock'
            external = False
            def classify(self, *args):
                raise AssertionError('Provider must not be called')
            def execute(self, *args):
                raise AssertionError('Provider must not be called')
        for provider in (Impostor(), MockProvider()):
            for decision in (None, True, SafetyDecision(False, True), SafetyDecision(True, False)):
                gate = lambda payload: decision
                system = MissionControlOS(provider=provider, safety_gate=gate, audit_log=None)
                with self.subTest(provider=type(provider).__name__, decision=decision), self.assertRaises(BlockedExecution):
                    system.run('synthetic')
        system = MissionControlOS(audit_log=None)
        system.provider = Impostor()
        with self.assertRaises(BlockedExecution):
            system.run('synthetic')

    def test_engine_rechecks_clearance_before_execution_and_revision(self):
        from tests.test_engine import RevisionProvider
        provider = RevisionProvider()
        seen = []
        def gate(payload):
            seen.append(payload)
            return SafetyDecision(True, len(seen) < 3)
        system = MissionControlOS(provider=provider, safety_gate=gate, audit_log=None)
        with self.assertRaises(BlockedExecution):
            system.run('synthetic')
        self.assertEqual(provider.calls, 1)  # Revision denied before provider receives it.
        self.assertEqual([item['operation'] for item in seen], ['classify','execute','execute'])
        self.assertTrue(seen[-1]['governance_feedback'])
        self.assertTrue(seen[0]['department_projections'])
        provider = RevisionProvider()
        decisions = iter((SafetyDecision(True, True), SafetyDecision(False, True)))
        with self.assertRaises(BlockedExecution):
            MissionControlOS(provider=provider, safety_gate=lambda payload: next(decisions), audit_log=None).run('synthetic')
        self.assertEqual(provider.calls, 0)

    def test_cli_sanitizes_filesystem_and_denied_provider_failures(self):
        for failure in (OSError('SYNTHETIC_PRIVATE_DETAIL'), BlockedExecution('SYNTHETIC_PRIVATE_DETAIL')):
            system = types.SimpleNamespace(run=lambda directive: None)
            system.run = unittest.mock.Mock(side_effect=failure)
            stdout, stderr = io.StringIO(), io.StringIO()
            with patch.object(main, 'MissionControlOS', return_value=system), patch('sys.stdout', stdout), patch('sys.stderr', stderr):
                self.assertEqual(main.main(['--demo','--no-log','--json']), 1)
            self.assertEqual(stdout.getvalue(), '')
            self.assertNotIn('SYNTHETIC_PRIVATE_DETAIL', stderr.getvalue())

    def test_absent_or_failing_engine_gate_blocks_before_provider_call(self):
        from unittest.mock import Mock
        provider = Mock()
        for gate in (None, Mock(side_effect=OSError('synthetic'))):
            with self.assertRaises(BlockedExecution):
                MissionControlOS(provider=provider, audit_log=None, safety_gate=gate).run('synthetic')
            provider.classify.assert_not_called()
            provider.execute.assert_not_called()

    def test_cli_default_denies_even_with_synthetic_credentials(self):
        import contextlib
        import sys
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.dict(sys.modules, {'openai': types.SimpleNamespace(OpenAI=FakeOpenAI)}), patch.dict(os.environ, {'OPENAI_API_KEY':'synthetic-test-only'}), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            status = main.main(['--demo','--provider','openai','--no-log'])
        self.assertEqual(status, 1)
        self.assertEqual(stdout.getvalue(), '')
        self.assertEqual(FakeOpenAI.last_instance.responses.calls, [])

    def test_retention_preserves_restrictive_mode(self):
        with tempfile.TemporaryDirectory() as folder:
            log, _ = self._audit_fixture(folder)
            log.path.chmod(0o400)
            original = log.path.read_bytes()
            log.purge_expired()
            self.assertEqual(log.retained_path.stat().st_mode & 0o777, 0o400)
            self.assertEqual(log.path.stat().st_mode & 0o777, 0o400)
            self.assertEqual(log.path.read_bytes(), original)

    def test_provider_route_subclass_cannot_override_confidence_validation(self):
        from mission_control.models import RouteDecision
        class InvalidRoute(RouteDecision):
            def __post_init__(self):
                pass
        provider = types.SimpleNamespace(
            classify=lambda *args: InvalidRoute('executive_strategy', 'synthetic', 2),
            execute=lambda *args: self.fail('Invalid confidence reached execution'),
        )
        with self.assertRaises(ValueError):
            MissionControlOS(provider=provider, safety_gate=synthetic_clearance, audit_log=None).run('synthetic')
