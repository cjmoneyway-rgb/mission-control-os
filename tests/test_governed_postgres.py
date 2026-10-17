"""Governed six-stage projection and rollback-only eligibility on the existing 34 tables."""
from dataclasses import asdict,replace
import json
import unittest
from unittest.mock import patch

from mission_control.connection_contracts import COMMAND_STAGES,COMMAND_ITEM_FIELDS,decode_request
from mission_control.connection_gateway import Budget
from mission_control.connection_services import PhaseOneServices
from mission_control.department_routing import seal
from mission_control.synthetic_identity import SyntheticGrant
from tests import test_postgres_integration as base_pg
from tests.pilot_pg_support import PilotFixture
from tests.pilot_support import TENANT,JOURNEY
from tests.connection_support import context,envelope,encoded
from tests.synthetic_postgres_support import session_ref


@unittest.skipUnless(base_pg.AVAILABLE,base_pg.REASON)
class GovernedPostgreSQLTests(PilotFixture,unittest.TestCase):
    def setUp(self):
        PilotFixture.setUp(self);self.services=PhaseOneServices(self.store)
    def request(self,action='journey.read',resource=JOURNEY,payload=None,revision=0,**changes):
        return decode_request(encoded(envelope(action,resource,payload,role='data_writer',revision=revision,**changes)))
    def project(self):
        ctx=context('data_writer');return self.services.command_center(self.request(),ctx,Budget(ctx))
    def eligible(self,request):
        ctx=context('data_writer');return self.services.eligibility(request,ctx,Budget(ctx))
    def proposal(self,event=None):return self.request('decision.submit',payload={'event':asdict(event or self.events[0])})

    def test_exact_stage_counts_and_required_fields(self):
        empty=self.project();self.assertEqual([q['stage'] for q in empty['queues']],list(COMMAND_STAGES))
        self.assertEqual([q['count'] for q in empty['queues']],[1,0,0,0,0,0])
        self.stage();value=self.project()
        self.assertEqual([q['count'] for q in value['queues']],[1,1,1,1,1,1])
        for queue in value['queues']:
            for item in queue['items']:
                self.assertEqual(set(item),COMMAND_ITEM_FIELDS)
                self.assertEqual(item['original_classification'],'syn-entry-class')
                self.assertEqual(item['current_stage'],queue['stage'])
                self.assertEqual(item['history_references'],[self.events[0].event_id])
        assignment=value['queues'][3]['items'][0]
        self.assertEqual(assignment['owning_department_reference'],self.departments[0].department_id)
        self.assertEqual(assignment['priority'],'syn-normal');self.assertIsNone(assignment['assigned_owner_reference'])
        self.assertIsNone(assignment['next_required_action']);self.assertEqual(assignment['risk_state'],'unresolved')
        self.assertIsNotNone(assignment['last_authorized_update'])
        with self.tx('approval_issuer') as tx:tx.revoke_event_approval(self.events[0].approval_reference);tx.commit()
        revoked=self.project()['queues'][3]
        self.assertEqual(revoked['blocked_count'],1)
        self.assertEqual(revoked['items'][0]['approval_state'],'unresolved')

    def test_pending_approval_and_dependencies_are_blocked_without_evidence_leak(self):
        self.prepare(approve=False);value=self.project();decision=value['queues'][2]
        self.assertEqual(decision['blocked_count'],1)
        self.assertEqual(decision['items'][0]['approval_state'],'unresolved')
        for forbidden in ('payload','proof','grantor_reference','policy_revision','guest_reference','evidence_references','rule_digest'):
            self.assertNotIn(forbidden,str(value))

    def test_hidden_and_cross_tenant_records_do_not_change_counts_or_shape(self):
        before=self.project()
        # A second journey is deliberately not granted to this reader.
        other=seal(replace(self.journey,journey_id='syn-hidden-journey',intake_reference='syn-hidden-intake'))
        intake=seal(replace(self.intake,event_id='syn-hidden-intake'))
        with self.admin() as connection:
            connection.execute("INSERT INTO mc_syn.routing_records SELECT tenant_reference,kind,%s,revision,previous_revision,%s,%s::jsonb,state,actor_reference,policy_revision,created_at,dataset FROM mc_syn.routing_records WHERE kind='intake' AND reference=%s",(intake.event_id,intake.content_digest,json.dumps(asdict(intake)),self.intake.event_id))
            connection.execute("INSERT INTO mc_syn.pilot_journeys SELECT tenant_reference,%s,%s,intake_kind,intake_revision,original_classification,%s::jsonb,%s,state,actor_reference,policy_revision,created_at,dataset FROM mc_syn.pilot_journeys WHERE reference=%s",(other.journey_id,intake.event_id,json.dumps(asdict(other)),other.content_digest,JOURNEY))
            connection.execute("INSERT INTO mc_syn.pilot_heads SELECT tenant_reference,%s,version,completed_stage,last_event_reference,progress,state,dataset FROM mc_syn.pilot_heads WHERE journey_reference=%s",(other.journey_id,JOURNEY))
            connection.commit()
        after=self.project();self.assertEqual(before,after)
        self.assertNotIn('syn-hidden',str(after));self.assertNotIn('syn-tenant-2',str(after))

    def test_eligibility_rehearsal_does_not_commit_proposal(self):
        value=self.eligible(self.proposal());self.assertTrue(value['eligible'],value['blocker_codes'])
        self.assertEqual(self.count('pilot_proposals'),0);self.assertEqual(self.count('pilot_events'),0)

    def test_unresolved_dependencies_and_stale_revision_fail_closed(self):
        event=seal(replace(self.events[0],dependency_references=('syn-missing-dependency',)))
        result=self.eligible(self.proposal(event));self.assertFalse(result['eligible']);self.assertEqual(result['blocker_codes'],['unresolved_dependencies'])
        self.prepare();result=self.eligible(self.proposal());self.assertFalse(result['eligible']);self.assertEqual(result['blocker_codes'],['stale_revision'])
        self.assertEqual(self.count('pilot_proposals'),1)

    def test_approval_revocation_invalidates_previously_eligible_advance(self):
        self.prepare()
        request=self.request('work-packet.create',payload={'event_reference':self.events[0].event_id,'proposal_revision':1})
        self.assertTrue(self.eligible(request)['eligible'])
        with self.tx('approval_issuer') as tx:tx.revoke_event_approval(self.events[0].approval_reference);tx.commit()
        self.assertFalse(self.eligible(request)['eligible']);self.assertEqual(self.count('pilot_events'),0)

    def test_authority_change_invalidates_prior_eligibility(self):
        request=self.proposal();self.assertTrue(self.eligible(request)['eligible'])
        with patch.object(self.authority,'authorize',side_effect=PermissionError('private-marker')):
            value=self.eligible(request)
        self.assertFalse(value['eligible']);self.assertEqual(value['blocker_codes'],['authorization_denied'])
        self.assertNotIn('private-marker',str(value));self.assertEqual(self.count('pilot_proposals'),0)

    def test_history_and_classification_are_immutable_under_projection(self):
        self.stage();first=self.project()
        with self.tx() as tx:before=tx.read_pilot(JOURNEY)
        self.project()
        with self.tx() as tx:after=tx.read_pilot(JOURNEY)
        self.assertEqual(before,after)
        self.stage(2);second=self.project()
        self.assertEqual(first['queues'][0]['items'][0]['history_references'],second['queues'][0]['items'][0]['history_references'][:1])
        self.assertEqual(second['queues'][0]['items'][0]['original_classification'],'syn-entry-class')

    def test_ui_source_rechecks_dependencies_inside_actual_mutation(self):
        event=seal(replace(self.events[0],dependency_references=('syn-missing-dependency',)))
        request=self.request('decision.submit',payload={'event':asdict(event)},source_surface='syn-command-center')
        ctx=context('data_writer')
        with self.assertRaises(PermissionError):self.services.execute(request,ctx,Budget(ctx))
        self.assertEqual(self.count('pilot_proposals'),0)

    def test_tenant_aggregates_use_only_the_authenticated_tenant(self):
        from tests.pilot_support import pilot_contracts
        self.stage()
        journey,intake,*_=pilot_contracts('syn-tenant-2')
        with self.tx('data_writer','syn-tenant-2') as tx:
            tx.start_journey(journey,intake,'syn-tenant-two-start');tx.commit()
        request=decode_request(encoded(envelope('journey.read',JOURNEY,role='data_writer',tenant='syn-tenant-2',revision=0)))
        ctx=context('data_writer','syn-tenant-2')
        other=self.services.command_center(request,ctx,Budget(ctx))
        self.assertEqual([queue['count'] for queue in other['queues']],[1,0,0,0,0,0])
        self.assertEqual([queue['count'] for queue in self.project()['queues']],[1,1,1,1,1,1])
        self.assertNotIn(self.events[0].event_id,str(other))

    def test_ui_confirmed_decision_and_approved_inactive_packet(self):
        from mission_control.command_center_ui import UIConfig,ROOT
        from tests.command_center_support import running_ui,session,ui_request
        from tests.connection_support import gateway_fixture
        from tests.test_command_center_ui import confirmed
        proposal=encoded(envelope('decision.submit',JOURNEY,{'event':asdict(self.events[0])},role='data_writer',revision=0))
        advance=encoded(envelope('work-packet.create',JOURNEY,{'event_reference':self.events[0].event_id,'proposal_revision':1},role='data_writer',revision=0))
        read=encoded(envelope('journey.read',JOURNEY,role='data_writer',revision=0))
        gateway,_,_=gateway_fixture(self.authority,self.services)
        with running_ui(gateway,UIConfig(reads=(read,),actions=(proposal,advance)),'data_writer') as (server,_):
            cookie,overview=session(server)
            def submit(reference):
                code,_,confirmation=ui_request(server,ROOT+'/api/prepare','POST',{'action_reference':reference,'csrf_token':overview['csrf_token']},cookie)
                self.assertEqual(code,200)
                return ui_request(server,ROOT+'/api/confirm','POST',confirmed(confirmation),cookie)
            self.assertEqual(submit('syn-ui-action-1')[0],200)
            self.assertEqual(self.count('pilot_proposals'),1);self.assertEqual(self.count('pilot_events'),0)
            with self.tx('approval_issuer') as tx:
                tx.issue_event_approval(JOURNEY,self.events[0].event_id,1,self.events[0].approval_reference);tx.commit()
            self.assertEqual(submit('syn-ui-action-2')[0],200)
            self.assertEqual(self.count('pilot_events'),1)
            code,_,value=ui_request(server,ROOT+'/api/overview',cookie=cookie)
            self.assertEqual(code,200);self.assertEqual([q['count'] for q in value['queues']],[1,1,1,1,1,1])

    def test_actual_stale_displayed_proposal_eligibility_is_rejected(self):
        from mission_control.command_center_ui import UIConfig,ROOT
        from tests.command_center_support import running_ui,session,ui_request
        from tests.connection_support import gateway_fixture
        from tests.test_command_center_ui import prepared,confirmed
        gateway,_,_=gateway_fixture(self.authority,self.services)
        config=UIConfig(actions=(encoded(envelope('decision.submit',JOURNEY,{'event':asdict(self.events[0])},role='data_writer',revision=0)),))
        with running_ui(gateway,config,'data_writer') as (server,_):
            cookie,overview=session(server);code,_,confirmation=prepared(server,cookie,overview);self.assertEqual(code,200)
            self.prepare()
            self.assertEqual(ui_request(server,ROOT+'/api/confirm','POST',confirmed(confirmation),cookie)[0],409)
            self.assertEqual(self.count('pilot_proposals'),1)

    def test_owner_acknowledgment_handoff_and_outcome_reuse_existing_services(self):
        from tests import pilot_pg_support
        from mission_control.command_center_ui import UIConfig,ROOT
        from tests.command_center_support import running_ui,session,ui_request
        from tests.connection_support import gateway_fixture
        from tests.test_command_center_ui import confirmed
        original=pilot_pg_support.pilot_authority
        def owner_authority():
            authority,custody=original()
            for tenant in (TENANT,'syn-tenant-2'):
                key=session_ref('data_reader',tenant);prior=authority.sessions[key]
                authority.sessions[key]=replace(prior,principal=replace(prior.principal,roles=('data_reader','data_writer')))
            return authority,custody
        with patch.object(pilot_pg_support,'pilot_authority',owner_authority):PilotFixture.setUp(self)
        packet_ref=self.stage()['packet_references'][0]
        with self.tx() as tx:packet=tx._get('packet',packet_ref,1)
        actions=[]
        for version,(action,field,attribute,value) in enumerate((
            ('assignment.acknowledge','acknowledgement_reference','outcome_references',self.events[1].outcome_references[0]),
            ('handoff.record','handoff_reference','handoff_references',self.events[1].handoff_references[0]),
            ('outcome.record','outcome_reference','outcome_references',self.events[2].outcome_references[0])),1):
            packet=seal(replace(packet,revision=version+1,**{attribute:(*getattr(packet,attribute),value)}))
            actions.append(encoded(envelope(action,packet_ref,{'packet':asdict(packet),field:value},role='data_reader',correlation=self.intake.event_id,revision=version)))
        gateway,_,_=gateway_fixture(self.authority,PhaseOneServices(self.store))
        read=encoded(envelope('visibility.project',packet_ref,{'audience':'command','team_reference':None},role='data_reader',correlation=self.intake.event_id))
        with running_ui(gateway,UIConfig(reads=(read,),actions=tuple(actions)),'data_reader') as (server,_):
            cookie,overview=session(server)
            for index in range(1,4):
                code,_,confirmation=ui_request(server,ROOT+'/api/prepare','POST',{'action_reference':'syn-ui-action-'+str(index),'csrf_token':overview['csrf_token']},cookie)
                self.assertEqual(code,200)
                self.assertEqual(confirmation['owning_department_reference'],self.departments[0].department_id)
                self.assertEqual(ui_request(server,ROOT+'/api/confirm','POST',confirmed(confirmation),cookie)[0],200)
            _,_,overview=ui_request(server,ROOT+'/api/overview',cookie=cookie)
            item=overview['queues'][3]['items'][0]
            self.assertEqual(item['revision'],4);self.assertEqual(item['assigned_owner_reference'],'syn-data_reader-'+TENANT)
            self.assertEqual(overview['queues'][5]['items'][0]['outcome_evidence_reference'],self.events[2].outcome_references[0])

    def test_revised_proposal_approval_is_projected_at_exact_event_revision(self):
        self.prepare(approve=False)
        revised=seal(replace(self.events[0],revision=2))
        self.prepare(event=revised);self.advance(event=revised)
        assignment=self.project()['queues'][3]
        self.assertEqual(assignment['blocked_count'],0)
        self.assertEqual(assignment['items'][0]['approval_state'],'synthetic_verified')
