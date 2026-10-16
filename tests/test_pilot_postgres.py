"""Real PostgreSQL 17.11 lifecycle, authorization and visibility proof."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
import threading
import unittest
from unittest.mock import patch

from mission_control.department_routing import seal
from mission_control.pilot_postgres import PILOT_COLUMNS, apply_pilot_migration
from mission_control.registry_persistence import ConflictError
from mission_control.synthetic_identity import SyntheticEvidenceCustody, SyntheticGrant
from mission_control.synthetic_postgres import _query
from tests import test_postgres_integration as base_pg
from tests.pilot_pg_support import PilotFixture
from tests.pilot_support import TENANT, JOURNEY
from tests.synthetic_postgres_support import session_ref


@unittest.skipUnless(base_pg.AVAILABLE,base_pg.REASON)
class PilotPostgreSQLTests(PilotFixture,unittest.TestCase):
    def test_forward_migration_checksum_and_thirty_four_tables(self):
        self.assertEqual(apply_pilot_migration(self.admin,self.authority,session_ref('migration_operator'),TENANT,1),'already_applied')
        with self.admin() as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM pg_tables WHERE schemaname='mc_syn'").fetchone()[0],34)
        with patch('mission_control.pilot_postgres.SQL_PATH') as path:
            path.read_text.return_value='-- changed synthetic migration'
            with self.assertRaises(ConflictError): apply_pilot_migration(self.admin,self.authority,session_ref('migration_operator'),TENANT,1)

    def test_full_sixteen_stage_journey_preserves_one_original_intake(self):
        results=self.complete_all()
        self.assertTrue(all(result['status']=='accepted' and result['state']=='inactive' for result in results))
        self.assertEqual(self.count('pilot_events'),16);self.assertEqual(self.count('pilot_decisions'),16)
        self.assertEqual(self.count('pilot_packet_links'),19);self.assertEqual(self.count('pilot_deliverables'),38)
        with self.tx() as tx:
            snapshot=tx.read_pilot(JOURNEY);history=tx.read_journey(self.intake.event_id)
            self.assertEqual((snapshot['head']['completed_stage'],snapshot['head']['progress']),(16,'completed'))
            self.assertTrue(all(row['original_classification']==self.journey.original_classification for row in snapshot['events']))
            self.assertTrue(all(row['original_classification']==self.journey.original_classification for row in history))
            self.assertEqual(len(tx._rows('routing_records',kind='intake')),1)
            for row in tx._pr('pilot_packet_links'):
                packet=tx._get('packet',row['packet_reference'],1)
                self.assertEqual(packet.original_classification,self.journey.original_classification)
                self.assertEqual(packet.source_event_reference,self.intake.event_id)

    def test_final_stage_can_close_without_operational_activation(self):
        for index in range(1,16): self.stage(index)
        event=seal(replace(self.events[-1],terminal_reference='syn-closed'))
        self.stage(16,event)
        with self.tx() as tx:
            head=tx.read_pilot(JOURNEY)['head'];self.assertEqual(head['progress'],'closed');self.assertEqual(head['state'],'inactive')

    def test_missing_dependencies_persist_blocked_attempt_without_packets(self):
        event=seal(replace(self.events[0],dependency_references=('syn-missing-dependency',)))
        self.prepare(event=event);result=self.advance(event=event)
        self.assertEqual(result['status'],'blocked');self.assertEqual(result['packet_references'],[])
        with self.tx() as tx:
            snapshot=tx.read_pilot(JOURNEY);self.assertEqual(snapshot['head']['completed_stage'],0)
            self.assertEqual(snapshot['head']['progress'],'blocked')
        self.assertEqual(self.count('pilot_packet_links'),0);self.assertEqual(self.count('pilot_deliverables'),0)
        self.assertEqual(self.advance(event=event),result)
        self.assertEqual(self.count('pilot_events'),1)

    def test_blocked_recovery_appends_a_separate_approved_attempt(self):
        blocked=seal(replace(self.events[0],dependency_references=('syn-missing-dependency',)))
        self.prepare(event=blocked);self.advance(event=blocked)
        retry=seal(replace(self.events[0],event_id='syn-pilot-retry-01',approval_reference='syn-pilot-retry-approval'))
        self.prepare(event=retry)
        result=self.advance(event=retry,version=1,key='syn-retry-key')
        self.assertEqual(result['status'],'accepted')
        with self.tx() as tx:
            snapshot=tx.read_pilot(JOURNEY)
            self.assertEqual([row['disposition'] for row in snapshot['events']],['blocked','accepted'])
            self.assertEqual(snapshot['head']['completed_stage'],1)

    def test_missing_event_approval_fails_closed(self):
        self.prepare(approve=False)
        with self.assertRaises(PermissionError): self.advance()
        self.assertEqual(self.count('pilot_events'),0)

    def test_revoked_event_approval_blocks_retries(self):
        event=self.prepare();self.advance()
        with self.tx('approval_issuer') as tx:
            self.assertEqual(tx.revoke_event_approval(event.approval_reference),'revoked')
            self.assertEqual(tx.revoke_event_approval(event.approval_reference),'duplicate');tx.commit()
        with self.assertRaises(PermissionError): self.advance()
        self.assertEqual(self.count('pilot_events'),1)

    def test_expired_event_evidence_fails(self):
        event=self.prepare(approve=False)
        with self.tx('approval_issuer') as tx:
            tx.issue_event_approval(JOURNEY,event.event_id,1,event.approval_reference,timedelta(microseconds=1));tx.commit()
        with self.assertRaises(PermissionError): self.advance()

    def test_unverifiable_event_custody_fails(self):
        self.prepare()
        self.store.custody=SyntheticEvidenceCustody(self.authority,session_ref('signing_custodian'),TENANT,1)
        with self.assertRaises(PermissionError): self.advance()

    def test_stale_proposal_revision_invalidates_original_approval(self):
        event=self.prepare();new=seal(replace(event,revision=2))
        with self.tx() as tx: tx.propose_event(new,1,'syn-revise-key');tx.commit()
        with self.assertRaises(PermissionError): self.advance()
        with self.assertRaises(PermissionError): self.advance(event=new)
        self.assertEqual(self.count('pilot_events'),0)

    def test_processed_events_cannot_be_revised(self):
        event=self.prepare();self.advance()
        with self.assertRaises(ConflictError):
            with self.tx() as tx: tx.propose_event(seal(replace(event,revision=2)),1,'syn-revise-key');tx.commit()

    def test_stale_registry_and_rule_revisions_fail(self):
        self.prepare()
        with self.tx() as tx: tx.append_department(seal(replace(self.departments[0],revision=2)),1);tx.commit()
        with self.assertRaises(PermissionError): self.advance()
        self.assertEqual(self.count('pilot_events'),0)

    def test_new_rule_revision_cannot_reuse_approved_old_revision(self):
        self.prepare()
        with self.tx() as tx: tx.append_rule(seal(replace(self.rules[0],revision=2)),1);tx.commit()
        with self.assertRaises(PermissionError): self.advance()

    def test_revoked_rule_approval_blocks_stage(self):
        self.prepare()
        with self.tx('approval_issuer') as tx: tx.revoke_routing_approval(self.rules[0].approval_reference);tx.commit()
        with self.assertRaises(PermissionError): self.advance()

    def test_incomplete_evidence_fails_before_routing(self):
        event=seal(replace(self.events[0],evidence_references=('syn-evidence-02',)))
        self.prepare(event=event)
        with self.assertRaises(ValueError): self.advance(event=event)
        self.assertEqual(self.count('pilot_events'),0)

    def test_invalid_transition_cannot_skip_qualification(self):
        self.prepare(2)
        with self.assertRaises(ValueError): self.advance(2,version=0)
        self.assertEqual(self.count('pilot_events'),0)

    def test_missing_predecessor_link_fails_even_after_first_stage(self):
        self.stage()
        event=seal(replace(self.events[1],previous_event_reference=None,dependency_references=()))
        self.prepare(2,event)
        with self.assertRaises(ValueError): self.advance(2,event)

    def test_stale_expected_journey_head_fails(self):
        self.prepare()
        with self.assertRaises(ConflictError): self.advance(version=7)
        self.assertEqual(self.count('pilot_events'),0)

    def test_exact_retries_and_duplicate_event_different_key(self):
        event=self.prepare();first=self.advance()
        with self.tx() as tx:
            self.assertEqual(tx.start_journey(self.journey,self.intake,'syn-start-key'),'duplicate');tx.commit()
        with self.assertRaises(ConflictError):
            with self.tx() as tx: tx.start_journey(self.journey,self.intake,'syn-other-entry-key');tx.commit()
        counts={name:self.count(name) for name in ('pilot_events','pilot_decisions','pilot_packet_links','pilot_deliverables','security_decisions')}
        self.assertEqual(self.advance(),first)
        with self.tx() as tx:
            self.assertEqual(tx.propose_event(event,0,'syn-propose-'+event.event_id+'-1'),'duplicate');tx.commit()
        self.assertEqual(counts,{name:self.count(name) for name in counts})
        with self.assertRaises(ConflictError): self.advance(key='syn-other-key')

    def test_idempotency_collision_with_changed_request_fails(self):
        self.prepare();self.advance()
        with self.assertRaises(ConflictError): self.advance(version=1)
        changed=seal(replace(self.events[0],revision=2))
        with self.assertRaises(ConflictError):
            with self.tx() as tx: tx.propose_event(changed,1,'syn-propose-'+changed.event_id+'-1');tx.commit()

    def test_concurrent_event_completion_has_one_packet_set(self):
        self.prepare();barrier=threading.Barrier(2)
        def advance(_):
            try:
                with self.tx() as tx:
                    barrier.wait(timeout=10);tx.advance_event(JOURNEY,self.events[0].event_id,1,0,'syn-advance-01');tx.commit()
                return 'committed'
            except ConflictError: return 'conflict'
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertCountEqual(list(pool.map(advance,(1,2))),['committed','conflict'])
        self.assertEqual(self.count('pilot_events'),1);self.assertEqual(self.count('pilot_packet_links'),1)

    def test_concurrent_proposal_revisions_use_compare_and_swap(self):
        event=self.prepare(approve=False);revision=seal(replace(event,revision=2));barrier=threading.Barrier(2)
        def append(index):
            try:
                with self.tx() as tx:
                    barrier.wait(timeout=10);tx.propose_event(revision,1,'syn-revise-'+str(index));tx.commit()
                return 'committed'
            except ConflictError: return 'conflict'
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertCountEqual(list(pool.map(append,(1,2))),['committed','conflict'])

    def test_interruption_and_missing_commit_roll_back_all_stage_outputs(self):
        self.prepare();self.advance(commit=False)
        self.assertEqual(self.count('pilot_events'),0)
        with self.assertRaises(ValueError):
            with self.tx() as tx:
                tx.advance_event(JOURNEY,self.events[0].event_id,1,0,'syn-advance-01');tx.commit()
                raise ValueError('Synthetic interruption')
        self.assertEqual(self.count('pilot_events'),0);self.assertEqual(self.count('pilot_packet_links'),0)

    def test_swallowed_failure_dooms_partial_stage_transaction(self):
        self.prepare()
        with self.assertRaises(PermissionError):
            with self.tx() as tx:
                tx.advance_event(JOURNEY,self.events[0].event_id,1,0,'syn-advance-01')
                try: tx.advance_event(JOURNEY,'syn-missing-event',1,1,'syn-other-key')
                except PermissionError: pass
        self.assertEqual(self.count('pilot_events'),0)

    def test_issuing_identity_revocation_before_commit_rolls_back(self):
        self.prepare();key=session_ref('approval_issuer');issuer=self.authority.sessions[key]
        policy=self.authority.policies[TENANT]
        for mutation in ('issuer','same-revision-policy'):
            try:
                with self.subTest(mutation=mutation),self.assertRaises(PermissionError):
                    with self.tx() as tx:
                        tx.advance_event(JOURNEY,self.events[0].event_id,1,0,'syn-advance-01')
                        if mutation=='issuer': self.authority.sessions[key]=replace(issuer,principal=replace(issuer.principal,revoked=True))
                        else: self.authority.policies[TENANT]=replace(policy,grants=(*policy.grants,SyntheticGrant('data_reader','packet.read','syn-extra-resource','deny')))
                        tx.commit()
            finally:
                self.authority.sessions[key]=issuer;self.authority.policies[TENANT]=policy
            self.assertEqual(self.count('pilot_events'),0)

    def test_unauthorized_visibility_role_cannot_start_advance_or_issue(self):
        self.prepare()
        for operation in ('start','advance','issue'):
            with self.subTest(operation=operation),self.assertRaises(PermissionError):
                with self.tx('data_reader') as tx:
                    if operation=='start': tx.start_journey(self.journey,self.intake,'syn-other-key')
                    elif operation=='advance': tx.advance_event(JOURNEY,self.events[0].event_id,1,0,'syn-advance-01')
                    else: tx.issue_event_approval(JOURNEY,self.events[0].event_id,1,self.events[0].approval_reference)

    def test_self_approval_and_combined_issuer_writer_identity_fail(self):
        event=self.prepare(approve=False);key=session_ref('approval_issuer');issuer=self.authority.sessions[key]
        self.authority.sessions[key]=replace(issuer,principal=replace(issuer.principal,subject_reference='syn-data_writer-'+TENANT,roles=('approval_issuer','data_writer')))
        with self.assertRaises(PermissionError):
            with self.tx('approval_issuer') as tx: tx.issue_event_approval(JOURNEY,event.event_id,1,event.approval_reference)

    def test_tenant_isolation_for_journey_reads_and_foreign_references(self):
        self.stage()
        with self.assertRaises(PermissionError):
            with self.tx(tenant='syn-tenant-2') as tx: tx.read_pilot(JOURNEY)
        with self.assertRaises(PermissionError):
            with self.store.transaction('syn-tenant-2',session_ref('data_writer'),1): pass
        with self.admin() as connection:
            with self.assertRaises(self.psycopg.IntegrityError):
                connection.execute("INSERT INTO mc_syn.pilot_packet_links SELECT 'syn-tenant-2',journey_reference,event_reference,packet_reference,packet_revision,packet_kind,state,dataset FROM mc_syn.pilot_packet_links")
            connection.rollback()

    def test_all_new_tables_have_default_deny_rls(self):
        self.stage();connection=self.store.factory()
        try:
            for table in PILOT_COLUMNS: self.assertEqual(_query(connection,'SELECT * FROM mc_syn.'+table)[0],[])
        finally: connection.close()
        with self.tx(tenant='syn-tenant-2') as tx:
            for table in PILOT_COLUMNS: self.assertEqual(_query(tx.connection,'SELECT * FROM mc_syn.'+table+' WHERE tenant_reference=%s',(TENANT,))[0],[])

    def test_subject_scoped_executive_and_team_visibility_does_not_leak(self):
        alpha=self.stage()['packet_references'][0];beta=self.stage(2)['packet_references'][0]
        with self.tx('data_reader') as tx:
            view=tx.view_packet(alpha,1,'executive');self.assertEqual(view['executive_reference'],'syn-executive-alpha')
            tx.distribute_team_visibility(alpha,1,'syn-team-alpha','syn-distribute-alpha');tx.commit()
        with self.tx('reader-beta') as tx:
            tx.distribute_team_visibility(beta,1,'syn-team-beta','syn-distribute-beta');tx.commit()
        for role,packet,team in (('data_reader',beta,'syn-team-beta'),('reader-beta',alpha,'syn-team-alpha')):
            for audience in ('executive','team'):
                with self.subTest(role=role,audience=audience),self.assertRaises(PermissionError):
                    with self.tx(role) as tx: tx.view_packet(packet,1,audience,team)
        with self.tx('data_reader') as tx:
            self.assertEqual(tx.view_packet(alpha,1,'team','syn-team-alpha')['audience'],'team')

    def test_oversight_is_minimized_and_never_grants_team_distribution(self):
        packet=self.stage()['packet_references'][0]
        with self.tx('data_reader') as tx:
            for audience in ('command','control','governance'):
                view=tx.view_packet(packet,1,audience)
                for key in ('guest_reference','evidence_references','proof','required_action','outcome_references','handoff_references'): self.assertNotIn(key,view)
        with self.assertRaises(PermissionError):
            with self.tx('reader-beta') as tx: tx.view_packet(packet,1,'command')
        with self.assertRaises(PermissionError):
            with self.tx() as tx: tx.distribute_team_visibility(packet,1,'syn-team-alpha','syn-distribute-alpha')

    def test_database_blocks_history_mutation_and_operational_state(self):
        self.stage()
        for table in ('pilot_journeys','pilot_proposals','pilot_events','pilot_decisions','pilot_evidence','pilot_packet_links','pilot_deliverables'):
            with self.subTest(table=table),self.assertRaises(RuntimeError):
                with self.tx() as tx: _query(tx.connection,'UPDATE mc_syn.'+table+" SET dataset='synthetic'");tx.commit()
        with self.assertRaises(RuntimeError):
            with self.tx() as tx: _query(tx.connection,"UPDATE mc_syn.pilot_heads SET state='active'");tx.commit()

        with self.assertRaises(RuntimeError):
            with self.tx() as tx:
                _query(tx.connection,"UPDATE mc_syn.pilot_heads SET version=version+1 WHERE journey_reference=%s",(JOURNEY,));tx.commit()
        # A faulty adapter that drops a handoff must fail at deferred DB commit.
        self.prepare(2)
        from mission_control.pilot_postgres import PilotTransaction
        original=PilotTransaction._pp
        def missing_handoff(tx,table,**values):
            if table=='pilot_deliverables' and values['kind']=='handoff': return
            return original(tx,table,**values)
        with patch('mission_control.pilot_postgres.PilotTransaction._pp',new=missing_handoff):
            with self.assertRaises(RuntimeError): self.advance(2)
        self.assertEqual(self.count('pilot_events'),1)

    def test_no_external_calls_engine_delivery_or_payload_audit(self):
        event=self.prepare()
        with patch('mission_control.providers.OpenAIProvider.classify',side_effect=AssertionError('External forbidden')), \
             patch('mission_control.providers.OpenAIProvider.execute',side_effect=AssertionError('External forbidden')), \
             patch('mission_control.engine.MissionControlOS.run',side_effect=AssertionError('Engine forbidden')):
            self.advance(event=event)
        with self.tx('audit_reviewer') as tx:
            for row in tx.read_security_decisions():
                self.assertNotIn('payload',row);self.assertNotIn('guest_reference',row);self.assertNotIn('proof',row)
