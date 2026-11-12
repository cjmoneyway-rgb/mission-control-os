"""Actual existing PostgreSQL services under optional synthetic contract guards.

No identity/session persistence table is added. Tests prove rollback, unchanged
archive boundaries and absence of new identity evidence in existing records.
"""
from dataclasses import asdict
import json
import threading
from concurrent.futures import ThreadPoolExecutor
import unittest

from mission_control.connection_services import PhaseOneServices
from mission_control.identity_sessions import ScopeRequirement,IdentityDenied
from mission_control.pilot_archive import TABLES
from mission_control.synthetic_postgres import _query
from tests.pilot_pg_support import PilotFixture
from tests.pilot_support import JOURNEY
from tests.connection_support import gateway_fixture,envelope,encoded
from tests.identity_session_support import bind_legacy


class IdentitySessionPostgreSQLTests(PilotFixture,unittest.TestCase):
    def install(self):
        requirements={('journey.pilot.read',JOURNEY):ScopeRequirement(('data_writer',)),
                      ('journey.pilot.propose',JOURNEY):ScopeRequirement(('data_writer',)),
                      ('registry.rule.read',self.events[0].rule_reference):ScopeRequirement(('data_writer',))}
        for reference,_,_,_ in self.rules[0].recipients:
            requirements[('registry.department.read',reference)]=ScopeRequirement(('data_writer',))
        a,c,s,g,ctx=bind_legacy(self.authority,requirements=requirements)
        gateway,_,_=gateway_fixture(self.authority,PhaseOneServices(self.store))
        return a,c,s,g,ctx,gateway
    def request(self):return encoded(envelope('decision.submit',JOURNEY,{'event':asdict(self.events[0])},role='data_writer',revision=0))
    def test_real_service_write_keeps_original_idempotency(self):
        a,c,s,g,ctx,gateway=self.install();raw=self.request()
        self.assertEqual(gateway.handle('POST','/v1/decisions',raw,ctx)[0],200)
        self.assertEqual(gateway.handle('POST','/v1/decisions',raw,ctx)[0],200)
        self.assertEqual(self.count('pilot_proposals'),1)
    def test_revoked_session_denies_before_persistence(self):
        a,c,s,g,ctx,gateway=self.install();a.revoke('syn-session',1)
        self.assertEqual(gateway.handle('POST','/v1/decisions',self.request(),ctx)[0],403)
        self.assertEqual(self.count('pilot_proposals'),0)
    def test_expired_session_denies_before_persistence(self):
        a,c,s,g,ctx,gateway=self.install();c.advance(900)
        self.assertEqual(gateway.handle('POST','/v1/decisions',self.request(),ctx)[0],403)
        self.assertEqual(self.count('pilot_proposals'),0)
    def test_revocation_before_commit_rolls_back_all_proposal_rows(self):
        a,c,s,g,ctx,gateway=self.install()
        before={name:self.count(name) for name in ('pilot_proposals','pilot_proposal_heads','routing_receipts','security_decisions')}
        with self.assertRaises((RuntimeError,PermissionError)):
            with self.tx() as tx:
                tx.propose_event(self.events[0],0,'syn-identity-rollback')
                rows,_=_query(tx.connection,'SELECT count(*) AS total FROM mc_syn.pilot_proposals')
                self.assertEqual(rows[0]['total'],1)
                a.revoke('syn-session',1);tx.commit()
        self.assertEqual(self.count('pilot_proposals'),0)
        self.assertEqual(self.count('pilot_proposal_heads'),0)
        for name,total in before.items():self.assertEqual(self.count(name),total)
    def test_domain_validation_failure_rolls_back(self):
        a,c,s,g,ctx,gateway=self.install()
        raw=encoded(envelope('decision.submit',JOURNEY,{'event':asdict(self.events[0])},role='data_writer',revision=5))
        self.assertNotEqual(gateway.handle('POST','/v1/decisions',raw,ctx)[0],200)
        self.assertEqual(self.count('pilot_proposals'),0)
    def test_raw_token_payload_never_reaches_database_or_archive_source(self):
        a,c,s,g,ctx,gateway=self.install();data=json.loads(self.request());data['payload']['access_token']='synthetic-rejected-raw-value'
        self.assertEqual(gateway.handle('POST','/v1/decisions',encoded(data),ctx)[0],400)
        with self.admin() as connection:
            for name in TABLES:
                rows,_=_query(connection,'SELECT row_to_json(t)::text AS value FROM mc_syn.'+name+' t')
                for row in rows:
                    for marker in ('synthetic-rejected-raw-value','syn-auth-context','syn-challenge-1','syn-external-1'):
                        self.assertNotIn(marker,row['value'])
        self.assertEqual(self.count('pilot_proposals'),0)
    def test_new_guard_cannot_issue_approval_or_migrate(self):
        a,c,s,g,ctx,gateway=self.install()
        with self.assertRaises(PermissionError):self.authority.authorize(ctx.session_reference,s.tenant_reference,1,'approval.pilot.issue',JOURNEY)
        with self.assertRaises(PermissionError):self.authority.authorize(ctx.session_reference,s.tenant_reference,1,'schema.migrate','syn-schema')
    def test_existing_policy_still_denies_cross_tenant(self):
        a,c,s,g,ctx,gateway=self.install();data=json.loads(self.request());data['tenant_reference']='syn-tenant-2'
        self.assertNotEqual(gateway.handle('POST','/v1/decisions',encoded(data),ctx)[0],200)
        self.assertEqual(self.count('pilot_proposals'),0)
    def test_complete_archive_contains_no_identity_receipts_or_raw_values(self):
        from mission_control.synthetic_identity import SyntheticAuthority
        from mission_control.pilot_postgres import PilotStore
        from mission_control.pilot_archive import export_complete_snapshot,validate_complete_archive
        from tests.synthetic_postgres_support import session_ref
        a,c,s,g,ctx,gateway=self.install()
        self.assertEqual(gateway.handle('POST','/v1/decisions',self.request(),ctx)[0],200)
        # Independent existing synthetic audit identity witnesses the SAME store.
        # It has its original exact backup grant, no contract identity data.
        witness=SyntheticAuthority(self.authority.sessions,self.authority.policies)
        store=PilotStore(self.store.factory,witness,self.custody)
        with store.transaction(s.tenant_reference,session_ref('audit_reviewer'),1) as tx:
            archive=export_complete_snapshot(tx,self.custody)
            validate_complete_archive(archive,self.custody)
        data=json.dumps(archive)
        for marker in ('syn-auth-context','syn-challenge-1','syn-external-1','synthetic-rejected-raw-value'):
            self.assertNotIn(marker,data)
