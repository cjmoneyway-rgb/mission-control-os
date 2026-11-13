"""Offline fictional contracts, M1 compatibility and strict negative boundaries."""
import ast
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace, FrozenInstanceError
from datetime import timedelta
import json
from pathlib import Path
import socket
import unittest
from unittest.mock import patch

from mission_control.hubspot_projection import (Observation, Mapping, MockProjection,
    Journal, ProjectionDenied, decode_observation, MAX_REQUESTS)
from mission_control.identity_sessions import ScopeRequirement
from scripts.demo_hubspot_projection import fixture


class ProjectionTests(unittest.TestCase):
    def setUp(self):
        self.e, self.identity, self.legacy, self.clock, self.ms, self.obs, self.session = fixture()
        self.addCleanup(self.identity.close)
        self.addCleanup(self.e.close)
        self.n = 0

    def call(self, o=None, expected=0, request=None, index=0, **changes):
        self.n += 1
        m = self.ms[index]
        args = dict(session=self.session, policy_revision=1, tenant=m.tenant_reference,
            mapping=m.mapping_reference, portal=m.portal_reference,
            request=request or 'syn-fictional-request-' + str(self.n), correlation='syn-fictional-correlation')
        if o is not None:
            args.update(fixture=(self.obs[o] if type(o) is int else o).observation_reference, expected_revision=expected)
        args.update(changes)
        return self.e.operate(**args)

    def raw(self, **changes):
        d = asdict(self.obs[0]); d.update(changes)
        return json.dumps(d).encode()

    def test_valid_strict_decode(self):
        self.assertEqual(decode_observation(self.raw()), self.obs[0])

    def test_duplicate_keys(self):
        with self.assertRaises(ProjectionDenied):
            decode_observation(self.raw()[:-1] + b',"dataset":"synthetic"}')

    def test_nonfinite_values(self):
        for value in (b'NaN', b'Infinity', b'-Infinity'):
            with self.subTest(value=value), self.assertRaises(ProjectionDenied):
                decode_observation(self.raw().replace(b'"source_version": 1', b'"source_version": ' + value))

    def test_invalid_utf8_and_unicode(self):
        for raw in (b'\xff', self.raw(object_reference='syn-fictional-\ud800')):
            with self.assertRaises(ProjectionDenied): decode_observation(raw)

    def test_prohibited_unknown_fields(self):
        for name in ('name','email','phone','address','notes','attachments','amount','custom','url','token',
                     'approval','roles','permissions','tenant','deal','relationship_lifecycle','instructions'):
            with self.subTest(name=name), self.assertRaises(ProjectionDenied):
                decode_observation(self.raw(**{name:'syn-fictional-forbidden'}))

    def test_size_depth_collection_limits(self):
        for raw in (b' ' * 16385, b'[' * 1500 + b'0' + b']' * 1500,
                    self.raw(status_references=['syn-fictional-x'] * 17),
                    self.raw(status_references=[{'nested':[]}])):
            with self.assertRaises(ProjectionDenied): decode_observation(raw)

    def test_wrong_types_and_missing_fields(self):
        for raw in (b'[]', b'{}', self.raw(source_version=True), self.raw(schema_version=True),
                    self.raw(status_references='syn-fictional-status-a')):
            with self.assertRaises(ProjectionDenied): decode_observation(raw)

    def test_unsupported_object_types(self):
        for kind in ('deal','user','relationship',None):
            with self.assertRaises(ProjectionDenied): decode_observation(self.raw(object_type=kind))

    def test_synthetic_declaration_not_safety_proof(self):
        for v in ('syn-person@example.invalid','syn-fictional-https://invalid','syn-fictional-<script>',
                  'syn-fictional-hidden\nvalue','syn-fictional-'+'a'*100):
            with self.assertRaises(ProjectionDenied): decode_observation(self.raw(object_reference=v))
        with self.assertRaises(ProjectionDenied): decode_observation(self.raw(dataset='production'))

    def test_reference_prefix_is_not_installation(self):
        with self.assertRaises(ProjectionDenied): self.call(fixture='syn-fictional-not-installed', expected_revision=0)

    def test_temporal_validation(self):
        for changes in ({'verified_at':'2026-01-01'}, {'source_updated_at':'2026-01-01T00:00:00+02:00'},
                        {'observed_at':(self.clock[0]-timedelta(seconds=1)).isoformat()}):
            with self.assertRaises(ProjectionDenied): decode_observation(self.raw(**changes))

    def test_frozen_records_and_projection(self):
        p = self.call(0)
        with self.assertRaises(FrozenInstanceError): p.state = 'approved'
        with self.assertRaises(FrozenInstanceError): self.obs[0].state = 'approved'

    def test_no_guard_or_untrusted_authority(self):
        for authority in (object(), None):
            with self.assertRaises(ProjectionDenied): MockProjection(authority,self.ms,self.obs,lambda:self.clock[0])
        self.legacy.contract_guard = None
        with self.assertRaises(ProjectionDenied): MockProjection(self.legacy,self.ms,self.obs,lambda:self.clock[0])

    def test_installation_limits_and_duplicate_maps(self):
        for ms, obs in (((),self.obs),(self.ms*9,self.obs),(self.ms+self.ms,self.obs),(self.ms,()),(self.ms,self.obs*12)):
            with self.assertRaises(ProjectionDenied): MockProjection(self.legacy,ms,obs,lambda:self.clock[0])

    def test_fixture_identifier_conflict_at_installation(self):
        bad = replace(self.obs[0],source_version=9)
        with self.assertRaises(ProjectionDenied): MockProjection(self.legacy,self.ms,self.obs+(bad,),lambda:self.clock[0])

    def test_installation_binding_and_allowlists(self):
        for changes in ({'portal_reference':'syn-fictional-other'}, {'object_reference':'syn-fictional-other'},
                        {'status_references':('syn-fictional-not-approved',)},
                        {'association_references':('syn-fictional-not-approved',)},
                        {'state':'merged','status_references':(),'association_references':(),
                         'merge_target':'syn-fictional-not-approved','tombstone_reference':'syn-fictional-tombstone'}):
            with self.assertRaises(ProjectionDenied):
                MockProjection(self.legacy,self.ms,(replace(self.obs[0],**changes),),lambda:self.clock[0])

    def test_tenant_portal_mapping_and_direct_object_denied(self):
        for changes in ({'tenant':'syn-fictional-other'}, {'portal':'syn-fictional-other'},
                        {'mapping':'syn-fictional-object-1'}, {'fixture':self.obs[6].observation_reference,'expected_revision':0}):
            with self.assertRaises(ProjectionDenied): self.call(**changes)
        self.assertFalse(self.e._current)

    def test_missing_and_unknown_session(self):
        for session in (None,'syn-fictional-unknown'):
            with self.assertRaises(ProjectionDenied): self.call(0,session=session)

    def test_expired_and_revoked_m1_session(self):
        self.identity.revoke('syn-fictional-contract-session',1)
        with self.assertRaises(ProjectionDenied): self.call(0)

    def test_inactivity_and_absolute_expiration(self):
        for seconds in (901,28801):
            e, ident, legacy, clock, ms, obs, session = fixture()
            try:
                clock[0] += timedelta(seconds=seconds)
                with self.assertRaises(ProjectionDenied):
                    e.operate(session,1,ms[0].tenant_reference,ms[0].mapping_reference,ms[0].portal_reference,
                              'syn-fictional-expired','syn-fictional-correlation')
            finally: e.close();ident.close()

    def test_revoked_legacy_principal(self):
        old=self.legacy.sessions[self.session]
        self.legacy.sessions[self.session]=replace(old,principal=replace(old.principal,revoked=True))
        with self.assertRaises(ProjectionDenied): self.call(0)

    def test_stale_policy_and_subject_revision(self):
        with self.assertRaises(ProjectionDenied): self.call(0,policy_revision=2)
        claim=next(iter(self.identity._subjects.values()))
        self.identity.revise_subject(replace(claim,revision=2),1)
        with self.assertRaises(ProjectionDenied): self.call(0)

    def test_exact_grant_and_deny_precedence(self):
        p=self.legacy.policies[self.ms[0].tenant_reference]
        self.legacy.policies[p.tenant]=replace(p,grants=tuple(replace(g,effect='deny') for g in p.grants))
        with self.assertRaises(ProjectionDenied): self.call(0)

    def test_missing_scope_and_forged_role(self):
        self.legacy.contract_guard.requirements.clear()
        with self.assertRaises(ProjectionDenied): self.call(0)
        self.legacy.contract_guard.requirements[('registry.read',self.ms[0].mapping_reference)]=ScopeRequirement(('data_writer',))
        with self.assertRaises(ProjectionDenied): self.call(0)

    def test_identity_substitution(self):
        old=self.legacy.sessions[self.session]
        self.legacy.sessions[self.session]=replace(old,principal=replace(old.principal,subject_reference=self.ms[0].object_reference))
        with self.assertRaises(ProjectionDenied): self.call(0)

    def test_identical_retry_and_digest(self):
        first=self.call(0,request='syn-fictional-same')
        self.assertEqual(first,self.call(0,request='syn-fictional-same'))
        self.assertEqual(first.observation_digest,self.obs[0].content_digest)
        self.assertEqual(first.projection_revision,1)

    def test_same_observation_deduplicated_across_requests(self):
        first=self.call(0)
        self.assertEqual(first,self.call(0,expected=1))
        self.assertEqual(len(self.e._current),1)

    def test_request_conflict_no_partial_state(self):
        self.call(0,request='syn-fictional-same');before=dict(self.e._current)
        with self.assertRaises(ProjectionDenied):self.call(1,request='syn-fictional-same')
        self.assertEqual(self.e._current,before)

    def test_duplicate_correlation_conflict(self):
        self.call(0,request='syn-fictional-same')
        with self.assertRaises(ProjectionDenied):self.call(0,request='syn-fictional-same',correlation='syn-fictional-changed')

    def test_expected_revision_and_boolean_denial(self):
        for expected in (1,True,-1,None):
            with self.assertRaises(ProjectionDenied):self.call(0,expected=expected)
        self.assertFalse(self.e._current)

    def test_out_of_order_and_stale_source(self):
        self.call(1)
        with self.assertRaises(ProjectionDenied):self.call(0,expected=1)

    def test_association_change_preserves_mapping_identity(self):
        first=self.call(0);second=self.call(1,expected=1)
        self.assertEqual(first.object_reference,second.object_reference)
        self.assertNotEqual(first.association_references,second.association_references)
        self.assertEqual(second.projection_revision,2)

    def test_unknown_and_unavailable_explicit(self):
        self.assertEqual(self.call().state,'unknown')
        for index in (4,5):
            e,ident,_,_,ms,obs,s=fixture()
            try:
                o=obs[index];p=e.operate(s,1,ms[0].tenant_reference,ms[0].mapping_reference,ms[0].portal_reference,
                    'syn-fictional-unavailable','syn-fictional-correlation',fixture=o.observation_reference,expected_revision=0)
                self.assertEqual(p.state,o.state);self.assertFalse(p.status_references)
            finally:e.close();ident.close()

    def test_freshness_expiry_and_duplicate_does_not_refresh(self):
        self.call(0,request='syn-fictional-same');self.clock[0]+=timedelta(seconds=301)
        self.assertEqual(self.call().state,'stale')
        self.assertFalse(self.call().association_references)
        with self.assertRaises(ProjectionDenied):self.call(0,request='syn-fictional-same')

    def test_equal_content_new_version_cannot_refresh(self):
        newer=replace(self.obs[0],observation_reference='syn-fictional-equal',source_version=2)
        e=MockProjection(self.legacy,self.ms,self.obs+(newer,),lambda:self.clock[0]);self.addCleanup(e.close)
        original=self.e;self.e=e
        self.call(0)
        with self.assertRaises(ProjectionDenied):self.call(newer,expected=1)
        self.e=original

    def test_tombstone_blocks_resurrection_and_old_retry(self):
        self.call(0,request='syn-fictional-old');p=self.call(2,expected=1)
        self.assertEqual(p.state,'deleted');self.assertFalse(p.association_references)
        for o,req in ((0,'syn-fictional-old'),(1,'syn-fictional-resurrect')):
            with self.assertRaises(ProjectionDenied):self.call(o,expected=0 if o==0 else 2,request=req)

    def test_merge_no_reparenting(self):
        self.call(0);p=self.call(3,expected=1)
        self.assertEqual(p.object_reference,self.ms[0].object_reference)
        self.assertEqual(p.merge_target,'syn-fictional-merge-target')
        self.assertEqual(p.state,'merged');self.assertFalse(p.status_references)
        with self.assertRaises(ProjectionDenied):self.call(1,expected=2)

    def test_invalid_merge_and_tombstone(self):
        for changes in ({'state':'merged'},{'state':'deleted'},{'merge_target':self.obs[0].object_reference},
                        {'state':'deleted','tombstone_reference':'syn-fictional-tombstone'}):
            with self.assertRaises(ProjectionDenied):decode_observation(self.raw(**changes))

    def test_source_revocation_blocks_reads_and_replay(self):
        self.call(0)
        m=self.ms[0];self.e.revoke_source(self.session,1,m.tenant_reference,m.mapping_reference,m.portal_reference,
                                       'syn-fictional-revoke','syn-fictional-correlation')
        with self.assertRaises(ProjectionDenied):self.call()
        with self.assertRaises(ProjectionDenied):self.call(0,expected=1)

    def test_audit_failure_no_partial_state(self):
        before=dict(self.e._current)
        with patch.object(self.e.journal,'append',side_effect=RuntimeError('private failure')):
            with self.assertRaisesRegex(ProjectionDenied,'^Fictional projection denied$'):self.call(0)
        self.assertEqual(before,self.e._current);self.assertFalse(self.e._requests)

    def test_audit_capacity_fails_closed(self):
        self.e.journal=Journal(1);self.call()
        with self.assertRaises(ProjectionDenied):self.call(0)
        self.assertFalse(self.e._current)

    def test_minimized_sanitized_audit_and_errors(self):
        self.call(0)
        with self.assertRaisesRegex(ProjectionDenied,'^Fictional projection denied$'):self.call(mapping='syn-fictional-secret-marker')
        rows=[asdict(v) for v in self.e.journal.snapshot()]
        text=json.dumps(rows)
        for forbidden in ('secret-marker','legacy-session','status_references','association_references','token','approval'):
            self.assertNotIn(forbidden,text)
        self.assertIsNone(rows[-1]['mapping_reference'])

    def test_clock_rollback_and_future_fixture(self):
        self.call();self.clock[0]-=timedelta(seconds=1)
        with self.assertRaises(ProjectionDenied):self.call()
        e,ident,_,clock,ms,obs,s=fixture()
        try:
            clock[0]-=timedelta(seconds=1)
            with self.assertRaises(ProjectionDenied):e.operate(s,1,ms[0].tenant_reference,ms[0].mapping_reference,
                ms[0].portal_reference,'syn-fictional-future','syn-fictional-correlation',fixture=obs[0].observation_reference,expected_revision=0)
        finally:e.close();ident.close()

    def test_concurrent_conflict_and_duplicate(self):
        def run(i):
            try:return self.call(0,request='syn-fictional-concurrent-'+str(i)).state
            except ProjectionDenied:return 'denied'
        with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(run,range(4)))
        self.assertEqual(results.count('active'),1);self.assertEqual(results.count('denied'),3)
        with ThreadPoolExecutor(max_workers=4) as pool:
            results=list(pool.map(lambda _:self.call(0,expected=1,request='syn-fictional-duplicate'),range(4)))
        self.assertTrue(all(p==results[0] for p in results))

    def test_request_capacity_no_eviction(self):
        self.e._requests={('syn-fictional-dummy',i):None for i in range(MAX_REQUESTS)}
        with self.assertRaises(ProjectionDenied):self.call(0)
        self.assertFalse(self.e._current)

    def test_restart_and_close_discard_only_mock_state(self):
        self.call(0);self.e.close()
        self.assertFalse(self.e._fixtures);self.assertFalse(self.e._requests);self.assertFalse(self.e._current)
        with self.assertRaises(ProjectionDenied):self.call()
        other=MockProjection(self.legacy,self.ms,self.obs,lambda:self.clock[0]);self.addCleanup(other.close)
        self.assertFalse(other._current)
        self.assertTrue(self.identity.snapshot())

    def test_no_network_credentials_or_domain_mutation(self):
        policies=dict(self.legacy.policies);sessions=dict(self.legacy.sessions)
        with patch.object(socket,'socket',side_effect=AssertionError('network forbidden')), \
             patch('builtins.open',side_effect=AssertionError('filesystem forbidden')), \
             patch('os.getenv',side_effect=AssertionError('credential lookup forbidden')):
            self.call(0);self.call(2,expected=1)
        self.assertEqual(policies,self.legacy.policies);self.assertEqual(sessions,self.legacy.sessions)
        source=Path('mission_control/hubspot_projection.py').read_text()
        for forbidden in ('requests','urllib','socket','psycopg','subprocess','os','providers'):
            tree=ast.parse(source)
            imports=[n for n in ast.walk(tree) if isinstance(n,(ast.Import,ast.ImportFrom))]
            self.assertFalse(any(forbidden in ast.unparse(n).split() for n in imports))

    def test_connectors_remain_disabled_and_operational_denial(self):
        from mission_control.connection_contracts import CONNECTORS
        self.assertEqual(len(CONNECTORS),7)
        for c in CONNECTORS:
            c.validate();self.assertFalse(c.enabled);self.assertEqual(c.state,'unresolved')
            with self.assertRaises(PermissionError):c.transmit()

    def test_request_reuse_across_objects_denied(self):
        self.call(0,request='syn-fictional-global-request')
        with self.assertRaises(ProjectionDenied):
            self.call(6,request='syn-fictional-global-request',index=1)
        self.assertEqual(len(self.e._current),1)

    def test_archived_blocks_resurrection(self):
        archived=replace(self.obs[2],state='archived',observation_reference='syn-fictional-archived')
        e=MockProjection(self.legacy,self.ms,self.obs+(archived,),lambda:self.clock[0])
        self.addCleanup(e.close);self.e=e
        self.call(0)
        self.assertEqual(self.call(archived,expected=1).state,'archived')
        with self.assertRaises(ProjectionDenied):self.call(1,expected=2)

    def test_audit_failure_does_not_withdraw_source(self):
        self.call(0)
        m=self.ms[0]
        with patch.object(self.e.journal,'append',side_effect=RuntimeError('private failure')):
            with self.assertRaises(ProjectionDenied):
                self.e.revoke_source(self.session,1,m.tenant_reference,m.mapping_reference,m.portal_reference,
                                     'syn-fictional-revoke','syn-fictional-correlation')
        self.assertFalse(self.e._revoked)
        self.assertEqual(self.call().state,'active')

    def test_guarded_projection_serializes_with_revocation(self):
        import threading
        entered=threading.Event();release=threading.Event();revoking=threading.Event();done=threading.Event()
        append=self.e.journal.append
        def blocked(row):
            if row.allowed:
                entered.set()
                if not release.wait(5):raise AssertionError('test synchronization expired')
            append(row)
        def revoke():
            revoking.set()
            self.identity.revoke('syn-fictional-contract-session',1)
            done.set()
        with patch.object(self.e.journal,'append',side_effect=blocked):
            with ThreadPoolExecutor(max_workers=2) as pool:
                admitted=pool.submit(self.call,0)
                try:
                    self.assertTrue(entered.wait(5))
                    revoker=pool.submit(revoke)
                    self.assertTrue(revoking.wait(5));self.assertFalse(done.is_set())
                finally:release.set()
                self.assertEqual(admitted.result().state,'active');revoker.result()
        self.assertTrue(done.is_set())
        with self.assertRaises(ProjectionDenied):self.call()

    def test_read_request_cannot_be_reused_for_replay(self):
        first=self.call(request='syn-fictional-read-id')
        self.assertEqual(first,self.call(request='syn-fictional-read-id'))
        with self.assertRaises(ProjectionDenied):self.call(0,request='syn-fictional-read-id')
        self.assertFalse(self.e._current)

    def test_old_read_request_cannot_return_superseded_projection(self):
        self.call(request='syn-fictional-old-read')
        self.call(0)
        with self.assertRaises(ProjectionDenied):self.call(request='syn-fictional-old-read')
