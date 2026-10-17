"""Connection adapter integration on the existing disposable PostgreSQL fixture."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
import threading
import unittest
from unittest.mock import patch

from mission_control.connection_gateway import Budget, Gateway, LocalContext, LocalRateLimit, SyntheticPolicyGate
from mission_control.connection_services import PhaseOneServices
from mission_control.department_routing import seal
from mission_control.pilot_postgres import PilotTransaction
from mission_control.pilot_archive import export_complete_snapshot
from tests import test_postgres_integration as base_pg
from tests import pilot_pg_support
from tests.connection_support import context, encoded, envelope, gateway_fixture
from tests.pilot_pg_support import PilotFixture
from tests.pilot_support import TENANT, JOURNEY
from tests.synthetic_postgres_support import session_ref


@unittest.skipUnless(base_pg.AVAILABLE,base_pg.REASON)
class ConnectionPostgreSQLTests(PilotFixture,unittest.TestCase):
    def setUp(self):
        PilotFixture.setUp(self)
        self.gateway,self.services,self.audit=gateway_fixture(self.authority,PhaseOneServices(self.store))

    def call(self,data,method='POST',path='/v1/decisions',role='data_writer',tenant=TENANT):
        return self.gateway.handle(method,path,encoded(data),context(role,tenant))

    def proposal_request(self,**changes):
        return envelope('decision.submit',JOURNEY,{'event':asdict(self.events[0])},role='data_writer',revision=0,**changes)

    def advance_request(self,index=1,revision=None,**changes):
        return envelope('work-packet.create',JOURNEY,
            {'event_reference':self.events[index-1].event_id,'proposal_revision':1},role='data_writer',
            revision=index-1 if revision is None else revision,**changes)

    def test_journey_retrieval_is_minimized_and_uses_existing_domain(self):
        data=envelope('journey.read',JOURNEY,role='data_writer',revision=0)
        code,body=self.call(data,'GET','/v1/journeys/'+JOURNEY)
        self.assertEqual(code,200);self.assertEqual(body['result']['events'],[])
        self.assertNotIn('guest_reference',str(body));self.assertNotIn('payload',body['result'])

    def test_cross_tenant_identity_fails_before_query(self):
        data=self.proposal_request();data['tenant_reference']='syn-tenant-2'
        self.assertIn(self.call(data)[0],(400,403));self.assertEqual(self.count('pilot_proposals'),0)

    def test_actor_spoofing_cannot_use_valid_service_context(self):
        data=self.proposal_request();data['actor_reference']='syn-other-actor'
        self.assertEqual(self.call(data)[0],403);self.assertEqual(self.count('pilot_proposals'),0)

    def test_decision_submission_appends_unapproved_proposal_only(self):
        code,body=self.call(self.proposal_request())
        self.assertEqual(code,200);self.assertEqual(body['result']['status'],'proposed')
        self.assertEqual(self.count('pilot_proposals'),1);self.assertEqual(self.count('pilot_evidence'),0)
        self.assertEqual(self.count('pilot_events'),0)

    def test_work_packet_creation_requires_existing_exact_event_approval(self):
        self.call(self.proposal_request())
        self.assertEqual(self.call(self.advance_request(),path='/v1/work-packets')[0],403)
        self.assertEqual(self.count('pilot_events'),0);self.assertEqual(self.count('pilot_packet_links'),0)

    def test_work_packet_creation_reuses_transactional_lifecycle(self):
        self.prepare();code,body=self.call(self.advance_request(),path='/v1/work-packets')
        self.assertEqual(code,200);self.assertEqual(body['result']['status'],'accepted')
        self.assertEqual(self.count('pilot_events'),1);self.assertEqual(self.count('pilot_packet_links'),1)
        self.assertEqual(self.count('pilot_decisions'),1)

    def test_identical_retry_does_not_duplicate_packets_or_history(self):
        self.prepare();data=self.advance_request()
        first=self.call(data,path='/v1/work-packets');data['request_id']='syn-request-retry'
        second=self.call(data,path='/v1/work-packets')
        self.assertEqual(first[0],200);self.assertEqual(second[0],200)
        self.assertEqual(first[1]['result'],second[1]['result'])
        self.assertEqual(self.count('pilot_events'),1);self.assertEqual(self.count('pilot_packet_links'),1)

    def test_duplicate_event_under_new_key_conflicts(self):
        self.prepare();self.call(self.advance_request(),path='/v1/work-packets')
        data=self.advance_request(idempotency_key='syn-other-key')
        self.assertEqual(self.call(data,path='/v1/work-packets')[0],409)
        self.assertEqual(self.count('pilot_events'),1)

    def test_concurrent_retries_commit_only_one_packet_set(self):
        self.prepare();data=self.advance_request();barrier=threading.Barrier(2)
        def run(_):
            barrier.wait();return self.call(data,path='/v1/work-packets')[0]
        with ThreadPoolExecutor(max_workers=2) as pool:codes=list(pool.map(run,range(2)))
        self.assertIn(200,codes);self.assertTrue(set(codes)<={200,409},codes)
        self.assertEqual(self.count('pilot_events'),1);self.assertEqual(self.count('pilot_packet_links'),1)

    def test_stale_expected_lifecycle_revision_fails_closed(self):
        self.stage();self.prepare(2)
        self.assertEqual(self.call(self.advance_request(2,revision=0),path='/v1/work-packets')[0],409)
        self.assertEqual(self.count('pilot_events'),1)

    def test_command_visibility_minimizes_payload_and_requires_policy(self):
        result=self.stage();packet=result['packet_references'][0]
        data=envelope('visibility.project',packet,{'audience':'command','team_reference':None},
            role='data_reader',correlation=self.intake.event_id)
        code,body=self.call(data,'GET','/v1/visibility',role='data_reader')
        self.assertEqual(code,200)
        self.assertFalse({'required_action','payload','facts','approval_reference'} & body['result'].keys())
        self.assertEqual(body['result']['state'],'inactive')

    def test_cross_department_reader_has_no_oversight_visibility(self):
        result=self.stage();packet=result['packet_references'][0]
        data=envelope('visibility.project',packet,{'audience':'command','team_reference':None},
            role='data_reader',correlation=self.intake.event_id,
            actor_reference='syn-reader-beta-'+TENANT,authentication_state_reference='syn-session-reader-beta-'+TENANT)
        ctx=LocalContext('syn-session-reader-beta-'+TENANT,1)
        self.assertEqual(self.gateway.handle('GET','/v1/visibility',encoded(data),ctx)[0],403)

    def test_cross_tenant_packet_reference_cannot_leak(self):
        packet=self.stage()['packet_references'][0]
        data=envelope('visibility.project',packet,{'audience':'command','team_reference':None},
            role='data_reader',tenant='syn-tenant-2',correlation=self.intake.event_id)
        code,body=self.call(data,'GET','/v1/visibility',role='data_reader',tenant='syn-tenant-2')
        self.assertEqual(code,403);self.assertNotIn(packet,str(body))

    def test_original_classification_cannot_be_replaced(self):
        data=envelope('classification.preserve',JOURNEY,{'original_classification':'syn-other'},role='data_writer',revision=0)
        self.assertEqual(self.call(data,path='/v1/classifications/preserve')[0],403)
        with self.tx() as tx:self.assertEqual(tx.read_pilot(JOURNEY)['journey']['original_classification'],'syn-entry-class')

    def test_outbox_only_prepares_reference_intention_for_visible_packet(self):
        packet=self.stage()['packet_references'][0]
        data=envelope('outbox.prepare',packet,{'connector_reference':'syn-slack','record_reference':packet},
            role='data_reader',correlation=self.intake.event_id)
        code,body=self.call(data,path='/v1/outbox',role='data_reader')
        self.assertEqual(code,200);self.assertEqual(body['inactive_outbox']['state'],'inactive')
        self.assertEqual(body['inactive_outbox']['record_reference'],packet)
        self.assertEqual(self.count('pilot_events'),1)
        with self.admin() as c:
            self.assertEqual(c.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='mc_syn'").fetchone()[0],34)

    def test_malformed_json_never_opens_database_connection(self):
        with patch.object(self.store,'factory',side_effect=AssertionError('No query')):
            self.assertEqual(self.gateway.handle('POST','/v1/decisions',b'{"x":1,"x":2}',context('data_writer'))[0],400)

    def test_audit_admission_failure_leaves_database_untouched(self):
        with patch.object(self.audit,'append',side_effect=OSError('syn-private-marker')):
            code,body=self.call(self.proposal_request())
        self.assertEqual(code,503);self.assertNotIn('syn-private-marker',str(body));self.assertEqual(self.count('pilot_proposals'),0)

    def test_cancellation_after_insert_rolls_back_transaction(self):
        ctx=context('data_writer');original=PilotTransaction.propose_event
        def cancel_after(tx,*args):
            result=original(tx,*args);ctx.cancelled.set();return result
        with patch.object(PilotTransaction,'propose_event',cancel_after):
            code,_=self.gateway.handle('POST','/v1/decisions',encoded(self.proposal_request()),ctx)
        self.assertEqual(code,408);self.assertEqual(self.count('pilot_proposals'),0)
        checks=[]
        original_check=Budget.check
        def deadline_after_insert(_budget):
            checks.append(True)
            if len(checks)==4: _budget.deadline=0
            original_check(_budget)
        with patch('mission_control.connection_gateway.Budget.check',deadline_after_insert):
            code,_=self.call(self.proposal_request())
        self.assertEqual(code,408);self.assertEqual(self.count('pilot_proposals'),0)

    def test_invalid_projection_before_commit_rolls_back(self):
        with patch('mission_control.connection_services.validate_projection',side_effect=ValueError('syn-private-marker')):
            code,body=self.call(self.proposal_request())
        self.assertEqual(code,400);self.assertNotIn('syn-private-marker',str(body));self.assertEqual(self.count('pilot_proposals'),0)

    def test_journey_revision_and_correlation_are_bound(self):
        for change in ({'expected_revision':1},{'correlation_reference':'syn-other-journey'}):
            data=envelope('journey.read',JOURNEY,role='data_writer',revision=0,**change)
            self.assertEqual(self.call(data,'GET','/v1/journeys/'+JOURNEY)[0],409)

    def test_service_identity_can_only_submit_inactive_proposal(self):
        data=envelope('decision.submit',JOURNEY,{'event':asdict(self.events[0])},role='service_writer',revision=0,actor_type='service')
        self.assertEqual(self.call(data,role='service_writer')[0],200)
        self.assertEqual(self.count('pilot_evidence'),0);self.assertEqual(self.count('pilot_events'),0)

    def test_intake_uses_existing_start_and_replays_without_second_entry(self):
        store,admin=self.new_empty_store()
        with self.tx('policy_admin',store=store) as tx:
            tx.bootstrap_policy();tx.register_reference('classification','syn-entry-class');tx.commit()
        gateway,_,_=gateway_fixture(self.authority,PhaseOneServices(store))
        data=envelope('intake',JOURNEY,{'journey':asdict(self.journey),'intake':asdict(self.intake)},role='data_writer',revision=0)
        for _ in range(2):self.assertEqual(gateway.handle('POST','/v1/intake',encoded(data),context('data_writer'))[0],200)
        with admin() as c:self.assertEqual(c.execute('SELECT count(*) FROM mc_syn.pilot_journeys').fetchone()[0],1)

    def test_stale_proposal_revision_is_not_accepted(self):
        data=self.proposal_request();data['expected_revision']=1
        self.assertEqual(self.call(data)[0],409);self.assertEqual(self.count('pilot_proposals'),0)

    def test_writer_cannot_acknowledge_without_department_ownership(self):
        packet=self.stage()['packet_references'][0]
        with self.tx() as tx:prior=tx._get('packet',packet,1)
        revised=seal(replace(prior,revision=2,outcome_references=(*prior.outcome_references,self.events[1].outcome_references[0])))
        data=envelope('assignment.acknowledge',packet,{'packet':asdict(revised),'acknowledgement_reference':self.events[1].outcome_references[0]},
            role='data_writer',correlation=self.intake.event_id)
        self.assertEqual(self.call(data,path='/v1/assignments/acknowledge')[0],403)
        with self.tx() as tx:self.assertEqual(tx._head('packet',packet),1)

    def test_explicit_owner_can_append_ack_outcome_handoff_and_archive(self):
        from mission_control.synthetic_identity import SyntheticGrant
        from mission_control.department_routing import derive_packets
        from tests.pilot_support import pilot_contracts
        authority_factory=pilot_pg_support.pilot_authority;references=pilot_pg_support.pilot_references
        def owned_authority():
            authority,custody=authority_factory()
            for tenant,policy in list(authority.policies.items()):
                key=session_ref('data_writer',tenant);session=authority.sessions[key]
                authority.sessions[key]=replace(session,principal=replace(session.principal,roles=('data_writer','data_reader')))
                journey,intake,departments,rules,_=pilot_contracts(tenant)
                preview=seal(replace(intake,event_id='syn-preview-intake',original_classification=rules[0].classification,fact_references=rules[0].preconditions))
                packets=derive_packets(preview,rules[0],{d.department_id:d for d in departments},'syn-key')
                extra=[SyntheticGrant('data_writer',action,packet.packet_id,'allow')
                       for packet in packets for action in ('packet.routing.append','packet.routing.read')]
                extra.append(SyntheticGrant('data_writer','packet.route_simulate',rules[0].rule_id,'allow'))
                authority.policies[tenant]=replace(policy,grants=(*policy.grants,*extra,SyntheticGrant('data_reader','packet.view.executive','syn-executive-alpha','allow',session.principal.subject_reference)))
            return authority,custody
        def owned_references(tenant):
            return [(kind,reference,'syn-data_writer-'+tenant if kind=='executive' and reference=='syn-executive-alpha' else parent)
                    for kind,reference,parent in references(tenant)]
        with patch.object(pilot_pg_support,'pilot_authority',owned_authority),patch.object(pilot_pg_support,'pilot_references',owned_references):
            PilotFixture.setUp(self)
        self.gateway,_,_=gateway_fixture(self.authority,PhaseOneServices(self.store))
        preview=seal(replace(self.intake,event_id='syn-preview-intake',original_classification=self.rules[0].classification,fact_references=self.rules[0].preconditions))
        before=self.count('routing_records')
        data=envelope('routing.preview',self.rules[0].rule_id,{'intake':asdict(preview),'rule_revision':1},
                      role='data_writer',correlation=preview.event_id)
        self.assertEqual(self.call(data,path='/v1/routing/preview')[0],200)
        self.assertEqual(self.count('routing_records'),before)
        conflicting=seal(replace(preview,event_id=self.intake.event_id))
        data['payload']['intake']=asdict(conflicting);data['correlation_reference']=self.intake.event_id
        self.assertEqual(self.call(data,path='/v1/routing/preview')[0],403)
        packet=self.stage()['packet_references'][0]
        for version,(action,field,value) in enumerate((
            ('assignment.acknowledge','acknowledgement_reference',self.events[1].outcome_references[0]),
            ('outcome.record','outcome_reference',self.events[2].outcome_references[0]),
            ('handoff.record','handoff_reference',self.events[1].handoff_references[0])),1):
            with self.tx() as tx:prior=tx._get('packet',packet,version)
            attribute='handoff_references' if action=='handoff.record' else 'outcome_references'
            revised=seal(replace(prior,revision=version+1,**{attribute:(*getattr(prior,attribute),value)}))
            data=envelope(action,packet,{'packet':asdict(revised),field:value},role='data_writer',correlation=self.intake.event_id,revision=version)
            path={'assignment.acknowledge':'/v1/assignments/acknowledge','outcome.record':'/v1/outcomes','handoff.record':'/v1/handoffs'}[action]
            self.assertEqual(self.call(data,path=path)[0],200)
        with self.tx('audit_reviewer') as tx:archive=export_complete_snapshot(tx,self.custody)
        self.assertEqual(len(archive['payload']['tables']),34)
        self.assertEqual(len([r for r in archive['payload']['tables']['routing_records'] if r['kind']=='packet']),4)
