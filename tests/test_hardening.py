"""Synthetic Phase 1A regression checks; no external transmissions."""
import contextlib
from dataclasses import replace
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import main
from mission_control import MissionControlOS
from mission_control.audit import JsonlAuditLog
from mission_control.contracts import Approval, RegistryRecord, WorkPacket, LifecycleEvent, JourneyHistory, digest
from mission_control.engine import BlockedExecution
from mission_control.models import RouteDecision
from mission_control.providers import OpenAIProvider, SafetyDecision
from tests.test_openai_provider import FakeOpenAI
from tests.hardening_support import SyntheticAuthority, synthetic_clearance
import types
import sys


class RejectedProvider:
    name = 'synthetic'
    def classify(self, directive, departments):
        return RouteDecision('executive_strategy', 'synthetic', 0.5)
    def execute(self, *args):
        return 'REJECTED_SYNTHETIC_CONTENT'


class HardeningTests(unittest.TestCase):
    def test_final_failure_blocks_and_audit_is_minimal(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'audit.jsonl'
            system = MissionControlOS(provider=RejectedProvider(), audit_log=path, safety_gate=synthetic_clearance)
            with self.assertRaises(BlockedExecution) as caught:
                system.run('PRIVATE_SYNTHETIC_DIRECTIVE')
            raw = path.read_text()
            self.assertNotIn('PRIVATE_SYNTHETIC', raw)
            self.assertNotIn('REJECTED_SYNTHETIC', raw)
            self.assertNotIn('REJECTED_SYNTHETIC', str(caught.exception))
            self.assertEqual(json.loads(raw)['status'], 'blocked')

    def test_cli_block_has_no_output(self):
        system = MissionControlOS(provider=RejectedProvider(), audit_log=None, safety_gate=synthetic_clearance)
        for mode in ([], ['--json']):
            stdout, stderr = io.StringIO(), io.StringIO()
            with patch.object(main, 'MissionControlOS', return_value=system), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                self.assertNotEqual(main.main(['--demo', '--no-log'] + mode), 0)
            self.assertEqual(stdout.getvalue(), '')
            self.assertNotIn('REJECTED_SYNTHETIC', stderr.getvalue())

    def test_confidence_strict(self):
        for value in (-0.1, 1.1, float('nan'), float('inf'), True, '0.5', None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                RouteDecision('synthetic', 'synthetic', value)
        for value in (0.0, 1.0):
            RouteDecision('synthetic', 'synthetic', value)

    def test_malformed_provider_results(self):
        provider = RejectedProvider()
        provider.classify = lambda *args: {'department_id': 'synthetic'}
        with self.assertRaises(ValueError):
            MissionControlOS(provider=provider, audit_log=None, safety_gate=synthetic_clearance).run('synthetic')
        provider = RejectedProvider()
        provider.execute = lambda *args: None
        with self.assertRaises(ValueError):
            MissionControlOS(provider=provider, audit_log=None, safety_gate=synthetic_clearance).run('synthetic')

    def test_approval_revision_and_authority(self):
        record = RegistryRecord('record-1', 1, 'department-ref', 'title-ref', 'owner-ref', 'policy-ref', 'active')
        with self.assertRaises(ValueError):
            record.validate()
        approval = Approval(record.record_id, 1, digest(record.payload()), 'evidence-ref')
        approved = replace(record, approval=approval)
        with self.assertRaises(ValueError):
            approved.validate()  # Self-asserted evidence grants no authority.
        authority = SyntheticAuthority(approval, {
            ('department', 'department-ref'), ('title', 'title-ref'),
            ('owner', 'owner-ref'), ('policy', 'policy-ref')})
        approved.validate(authority)
        for changed in (replace(approved, revision=2), replace(approved, title_reference='changed'), replace(approved, owner_reference=None), replace(approved, policy_reference='unresolved')):
            with self.assertRaises(ValueError):
                changed.validate(authority)

    def test_lifecycle_append_only_and_duplicates(self):
        registry = {'record-1': RegistryRecord('record-1', 1, None)}
        packet = WorkPacket('packet-1', 'record-1', 1, 'synthetic action')
        event = LifecycleEvent('event-1', 'journey-1', 'new', 'received', packet)
        history = JourneyHistory()
        history.append(event, registry)
        snapshot = history.events
        for invalid in (event, replace(event, event_id='event-2', next_state='completed'), replace(event, event_id='event-2', active=True)):
            with self.assertRaises(ValueError):
                history.append(invalid, registry)
        self.assertEqual(history.events, snapshot)
        history.append(replace(event, event_id='event-2', previous_state='received', next_state='prepared'), registry)
        self.assertEqual(len(snapshot), 1)
        self.assertEqual(len(history.events), 2)
        for invalid in (replace(packet, registry_reference='missing'), replace(packet, registry_revision=2), replace(packet, state='active')):
            with self.assertRaises(ValueError):
                invalid.validate(registry)

    def test_provider_gate_precedes_transmission(self):
        with patch.dict(sys.modules, {'openai': types.SimpleNamespace(OpenAI=FakeOpenAI)}):
            for decision in (None, True, SafetyDecision(False, True), SafetyDecision(True, False)):
                provider = OpenAIProvider(safety_gate=lambda payload: decision)
                with self.assertRaises(RuntimeError):
                    provider._respond('synthetic instructions', 'synthetic directive')
                self.assertEqual(provider.client.responses.calls, [])

    def test_retention_and_redaction(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'audit.jsonl'
            system = MissionControlOS(audit_log=path)
            record = system.run('SYNTHETIC_DIRECTIVE')
            raw = path.read_text()
            self.assertNotIn('SYNTHETIC_DIRECTIVE', raw)
            self.assertNotIn('department', raw)
            record.created_at = '2000-01-01T00:00:00+00:00'
            log = JsonlAuditLog(path, retention_days=1)
            log.append(record)
            original = path.read_bytes()
            result = log.purge_expired()
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(len(path.read_text().splitlines()), 2)
            self.assertEqual(len(log.retained_path.read_text().splitlines()), 1)
            self.assertEqual(result['expired_count'], 1)

    def test_malformed_projection(self):
        from mission_control.config import load_departments
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'projection.json'
            for payload in ([], {'departments': {}}, {'departments': [{}]}):
                path.write_text(json.dumps(payload))
                with self.assertRaises(ValueError):
                    load_departments(path)

    def test_live_response_shape_and_confidence(self):
        from mission_control.config import load_departments
        with patch.dict(sys.modules, {'openai': types.SimpleNamespace(OpenAI=FakeOpenAI)}):
            provider = OpenAIProvider(safety_gate=lambda payload: SafetyDecision(True, True))
            for raw in ('not json', '[]', '{}', '{"department_id": "synthetic", "rationale": "synthetic", "confidence": "0.5"}', '{"department_id": "synthetic", "rationale": "synthetic", "confidence": 2}'):
                with self.subTest(raw=raw), patch.object(provider, '_respond', return_value=raw), self.assertRaises(RuntimeError) as caught:
                    provider.classify('synthetic', load_departments())
                self.assertNotIn(raw, str(caught.exception))
            for output in (None, 42, '', '   '):
                with patch.object(provider.client.responses, 'create', return_value=types.SimpleNamespace(output_text=output)), self.assertRaises(RuntimeError):
                    provider._respond('synthetic', 'synthetic')

    def test_registry_states_and_evidence(self):
        record = RegistryRecord('record-1', 1, None)
        for invalid in (replace(record, state='unknown'), replace(record, revision=True), replace(record, state='active')):
            with self.assertRaises(ValueError):
                invalid.validate()
        approval = Approval('record-1', True, digest(record.payload()), 'evidence-ref')
        with self.assertRaises(ValueError):
            approval.validate('record-1', 1, record.payload())

    def test_bad_retention_preserves_log(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'audit.jsonl'
            path.write_text('not-json\n')
            with self.assertRaises(ValueError):
                JsonlAuditLog(path, retention_days=1).purge_expired()
            self.assertEqual(path.read_text(), 'not-json\n')
            with self.assertRaises(ValueError):
                JsonlAuditLog(path, retention_days=0)
