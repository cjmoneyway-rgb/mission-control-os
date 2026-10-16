"""Synthetic-only foundation tests; no storage, network, or identity provider."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import types
import unittest

from mission_control.contracts import LifecycleEvent, RegistryRecord, WorkPacket, digest
from mission_control.registry_authorization import (
    AccessRequest, PermissionRule, PolicySnapshot, Principal, RegistryAuthorization)
from mission_control.registry_migrations import load_migration, validate_migration
from mission_control.registry_persistence import (
    ConflictError, IdempotencyReceipt, JournalEvent, PacketRevision, RegistryRevision,
    validate_event_append, validate_registry_append)


MIGRATION = Path(__file__).resolve().parents[1] / 'migrations/protected_registry/0001_foundation.json'


def fixtures():
    record = RegistryRecord('syn-registry-1', 1, None)
    registry = RegistryRevision('syn-tenant-1', record, 0, digest(record.payload()))
    packet = PacketRevision('syn-tenant-1', 1, 0,
                            WorkPacket('syn-packet-1', record.record_id, 1, 'Synthetic validation'),
                            'syn-source-1', 'syn-purpose-1', 'syn-policy-1')
    event = JournalEvent('syn-tenant-1', 1,
                         LifecycleEvent('syn-event-1', 'syn-journey-1', 'new', 'received', packet.packet))
    return registry, packet, event


class AuthorizationTests(unittest.TestCase):
    def setUp(self):
        now = datetime.now(timezone.utc)
        self.principal = Principal('syn-subject-1', 'syn-tenant-1', 'mission-control-registry',
                                   ('registry_editor',), now-timedelta(minutes=1),
                                   now+timedelta(minutes=5), False)
        self.rule = PermissionRule('registry_editor', 'registry.append_draft', 'syn-registry-1', 'allow')
        self.policy = PolicySnapshot('syn-tenant-1', 1, (self.rule,),
                                     now-timedelta(minutes=1), now+timedelta(minutes=5))
        self.identity = types.SimpleNamespace(resolve_session=lambda reference: self.principal if reference == 'syn-session-1' else None)
        self.policies = types.SimpleNamespace(resolve_policy=lambda tenant: self.policy)
        self.boundary = RegistryAuthorization(self.identity, self.policies)
        self.request = AccessRequest('syn-session-1', 'syn-tenant-1', 'registry.append_draft', 'syn-registry-1', 1)

    def test_unconfigured_and_forged_sessions_deny(self):
        self.assertFalse(RegistryAuthorization().check(self.request).allowed)
        self.assertFalse(self.boundary.check(replace(self.request, session_reference='forged')).allowed)
        self.identity.resolve_session = lambda reference: {'roles':['registry_editor']}
        self.assertFalse(self.boundary.check(self.request).allowed)

    def test_exact_permission_and_deny_override(self):
        self.assertTrue(self.boundary.check(self.request).allowed)
        self.assertFalse(self.boundary.check(replace(self.request, resource_reference='syn-registry-2')).allowed)
        self.policy = replace(self.policy, rules=(self.rule, replace(self.rule, effect='deny')))
        self.assertFalse(self.boundary.check(self.request).allowed)
        self.policy = replace(self.policy, rules=())
        self.assertFalse(self.boundary.check(self.request).allowed)

    def test_identity_scope_expiry_revocation_and_roles(self):
        original = self.principal
        cases = [replace(original, tenant_reference='syn-tenant-2'),
                 replace(original, audience='different-audience'),
                 replace(original, revoked=True), replace(original, revoked=0),
                 replace(original, expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)),
                 replace(original, valid_from=datetime.now(timezone.utc)+timedelta(days=1)),
                 replace(original, expires_at=datetime.now()),
                 replace(original, roles=('ungranted_role',)), replace(original, roles=['registry_editor'])]
        for principal in cases:
            self.principal = principal
            with self.subTest(principal=principal):
                self.assertFalse(self.boundary.check(self.request).allowed)

    def test_stale_cross_tenant_or_expired_policy_deny(self):
        self.assertFalse(self.boundary.check(replace(self.request, policy_revision=2)).allowed)
        original = self.policy
        for policy in (replace(original, tenant_reference='syn-tenant-2'),
                       replace(original, expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)),
                       replace(original, rules=(replace(self.rule, resource_reference='*'),))):
            self.policy = policy
            self.assertFalse(self.boundary.check(self.request).allowed)

    def test_unsupported_actions_or_real_dataset_never_grant(self):
        for action in ('registry.activate','approval.issue','provider.external_use','pilot.start'):
            with self.subTest(action=action):
                self.assertFalse(self.boundary.check(replace(self.request, action=action)).allowed)
        self.assertFalse(self.boundary.check(replace(self.request, dataset='operational')).allowed)
        self.assertFalse(self.boundary.check(replace(self.request, policy_revision=True)).allowed)

    def test_authority_outage_is_sanitized_denial(self):
        def failure(reference):
            raise RuntimeError('SYNTHETIC_PRIVATE_ERROR')
        self.identity.resolve_session = failure
        decision = self.boundary.check(self.request)
        self.assertFalse(decision.allowed)
        self.assertNotIn('SYNTHETIC_PRIVATE_ERROR', repr(decision))
        self.assertIsNone(decision.subject_reference)


class PersistenceContractTests(unittest.TestCase):
    def setUp(self):
        self.registry, self.packet, self.event = fixtures()

    def test_valid_inactive_contracts_and_registry_cas(self):
        self.registry.validate()
        self.packet.validate(self.registry)
        self.assertEqual(validate_event_append(self.event, None, None, self.packet, self.registry), 'append')
        validate_registry_append(self.registry, None)
        record2 = replace(self.registry.record, revision=2)
        second = replace(self.registry, record=record2, previous_revision=1, content_digest=digest(record2.payload()))
        validate_registry_append(second, self.registry)
        for stale in (self.registry, replace(second, previous_revision=0)):
            with self.assertRaises(ValueError):
                validate_registry_append(stale, self.registry)
        with self.assertRaises(ConflictError):
            validate_registry_append(replace(second, tenant_reference='syn-tenant-2'), self.registry)

    def test_registry_tamper_or_activation_is_rejected(self):
        for invalid in (replace(self.registry, content_digest='0'*64),
                        replace(self.registry, dataset='operational'),
                        replace(self.registry, schema_revision=True),
                        replace(self.registry, previous_revision=True),
                        replace(self.registry, record=replace(self.registry.record, state='active'))):
            with self.assertRaises(ValueError):
                invalid.validate()

    def test_packet_cross_tenant_unknown_revision_and_activation(self):
        for invalid in (replace(self.packet, tenant_reference='syn-tenant-2'),
                        replace(self.packet, packet=replace(self.packet.packet, registry_revision=2)),
                        replace(self.packet, packet=replace(self.packet.packet, registry_reference='missing')),
                        replace(self.packet, packet=replace(self.packet.packet, state='active')),
                        replace(self.packet, revision=True), replace(self.packet, source_reference=''),
                        replace(self.packet, schema_revision=True)):
            with self.assertRaises(ValueError):
                invalid.validate(self.registry)

    def test_exact_retry_and_changed_payload_collision(self):
        self.assertEqual(validate_event_append(self.event, self.event, self.event, self.packet, self.registry), 'duplicate')
        changed = replace(self.event, event=replace(self.event.event, journey_reference='syn-other-journey'))
        with self.assertRaises(ConflictError):
            validate_event_append(changed, None, self.event, self.packet, self.registry)
        with self.assertRaises(ConflictError):
            validate_event_append(self.event, None, replace(self.event, tenant_reference='syn-tenant-2'), self.packet, self.registry)

    def test_ordered_history_stale_chain_and_terminal_state(self):
        second = replace(self.event, sequence=2, previous_digest=self.event.content_digest,
                         event=replace(self.event.event, event_id='syn-event-2', previous_state='received', next_state='prepared'))
        self.assertEqual(validate_event_append(second, self.event, None, self.packet, self.registry), 'append')
        third = replace(second, sequence=3, previous_digest=second.content_digest,
                        event=replace(second.event, event_id='syn-event-3', previous_state='prepared', next_state='completed'))
        self.assertEqual(validate_event_append(third, second, None, self.packet, self.registry), 'append')
        for bad in (replace(second, sequence=3), replace(second, previous_digest='0'*64),
                    replace(second, event=replace(second.event, next_state='completed'))):
            with self.assertRaises(ConflictError):
                validate_event_append(bad, self.event, None, self.packet, self.registry)
        with self.assertRaises(ConflictError):
            validate_event_append(third, third, None, self.packet, self.registry)
        with self.assertRaises(ConflictError):
            validate_event_append(second, replace(self.event, tenant_reference='syn-tenant-2'), None, self.packet, self.registry)

    def test_inactive_events_only_and_idempotency_contract(self):
        for invalid in (replace(self.event, event=replace(self.event.event, active=True)),
                        replace(self.event, sequence=True), replace(self.event, previous_digest='0'*64),
                        replace(self.event, dataset='operational'), replace(self.event, schema_revision=True)):
            with self.assertRaises(ValueError):
                invalid.validate(self.packet, self.registry)
        receipt = IdempotencyReceipt('syn-tenant-1','journey.append_inactive','syn-key-1',self.event.content_digest,'syn-event-1',1)
        receipt.validate()
        for invalid in (replace(receipt, payload_digest='bad'), replace(receipt, operation='registry.activate'),
                        replace(receipt, result_revision=True)):
            with self.assertRaises(ValueError):
                invalid.validate()


class LogicalMigrationTests(unittest.TestCase):
    def test_manifest_integrity_and_immutable_plan(self):
        plan = load_migration(MIGRATION)
        checksum = plan.checksum
        changed = plan.manifest
        changed['dataset'] = 'operational'
        self.assertEqual(plan.checksum, checksum)
        self.assertEqual(plan.manifest['dataset'], 'synthetic')
        self.assertEqual(len(plan.manifest['entities']), 14)

    def test_unsafe_or_incomplete_migrations_rejected(self):
        original = load_migration(MIGRATION).manifest
        changes=[]
        bad=deepcopy(original);bad['dataset']='operational';changes.append(bad)
        bad=deepcopy(original);bad['from_revision']=True;changes.append(bad)
        bad=deepcopy(original);bad['seed_records']=[];changes.append(bad)
        bad=deepcopy(original);bad['entities'].pop();changes.append(bad)
        bad=deepcopy(original);bad['entities'][0]['primary_key']=['migration_id'];changes.append(bad)
        bad=deepcopy(original);bad['entities'][0]['name']='invalid;name';changes.append(bad)
        bad=deepcopy(original);bad['entities'][0]['columns'].pop('dataset');changes.append(bad)
        bad=deepcopy(original);bad['entities'][4]['rules'].remove('inactive_only');changes.append(bad)
        bad=deepcopy(original);bad['entities'][0]['rules'].append('grant_all');changes.append(bad)
        bad=deepcopy(original);bad['entities'][4]['rules'].remove('append_only');changes.append(bad)
        bad=deepcopy(original);bad['entities'][5]['rules'].remove('compare_and_swap');changes.append(bad)
        bad=deepcopy(original);bad['entities'][4]['columns'].pop('state');changes.append(bad)
        bad=deepcopy(original);bad['entities'][3]['foreign_keys'][0]['columns'].remove('tenant_reference');changes.append(bad)
        bad=deepcopy(original);bad['entities'][3]['foreign_keys'][0]['target']='missing';changes.append(bad)
        for document in changes:
            with self.subTest(document_index=changes.index(document)), self.assertRaises(ValueError):
                validate_migration(document)

    def test_duplicate_migration_keys_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'manifest.json'
            path.write_text('{"dataset":"synthetic","dataset":"operational"}')
            with self.assertRaises(ValueError):
                load_migration(path)


class PacketVersionBindingTests(unittest.TestCase):
    def test_event_digest_and_replay_bind_exact_packet_revision(self):
        registry, packet1, event1 = fixtures()
        packet2 = replace(packet1, revision=2, previous_revision=1, source_reference='syn-source-2')
        packet2.validate(registry)
        with self.assertRaises(ValueError):
            event1.validate(packet2, registry)
        event2 = replace(event1, packet_revision=2)
        event2.validate(packet2, registry)
        self.assertNotEqual(event1.content_digest, event2.content_digest)
        with self.assertRaises(ConflictError):
            validate_event_append(event2, None, event1, packet2, registry)
