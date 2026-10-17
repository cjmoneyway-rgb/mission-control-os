"""Ephemeral HTTP requests through unchanged gateway/services and real PostgreSQL."""
from dataclasses import asdict
import json
import time
import unittest
from unittest.mock import patch

from mission_control.connection_services import PhaseOneServices
from mission_control.pilot_archive import export_complete_snapshot
from tests import test_postgres_integration as base_pg
from tests.connection_support import envelope, gateway_fixture
from tests.local_http_support import running, request
from tests.pilot_pg_support import PilotFixture
from tests.pilot_support import JOURNEY


@unittest.skipUnless(base_pg.AVAILABLE, base_pg.REASON)
class LocalHTTPPostgreSQLTests(PilotFixture, unittest.TestCase):
    def setUp(self):
        PilotFixture.setUp(self)
        self.gateway, self.services, self.audit = gateway_fixture(self.authority, PhaseOneServices(self.store))

    def proposal(self, **changes):
        return envelope('decision.submit',JOURNEY,{'event':asdict(self.events[0])},
                        role='data_writer',revision=0,**changes)

    def call(self,data,method='POST',path='/v1/decisions',role='data_writer',**server_options):
        with running(self.gateway,role=role,**server_options) as (server,binding):
            code,headers,raw=request(server,binding,data,method=method,path=path)
            return code,json.loads(raw)

    def advance_request(self,**changes):
        return envelope('work-packet.create',JOURNEY,
            {'event_reference':self.events[0].event_id,'proposal_revision':1},
            role='data_writer',revision=0,**changes)

    def test_http_proposal_and_retry_use_existing_receipts(self):
        data=self.proposal()
        self.assertEqual(self.call(data)[0],200)
        data['request_id']='syn-request-retry'
        self.assertEqual(self.call(data)[0],200)
        self.assertEqual(self.count('pilot_proposals'),1)
        self.assertEqual(self.count('pilot_events'),0)

    def test_http_approval_required(self):
        self.assertEqual(self.call(self.proposal())[0],200)
        self.assertEqual(self.call(self.advance_request(),path='/v1/work-packets')[0],403)
        self.assertEqual(self.count('pilot_events'),0)

    def test_http_approved_advance_and_idempotent_retry(self):
        self.prepare()
        first=self.call(self.advance_request(),path='/v1/work-packets')
        second=self.call(self.advance_request(request_id='syn-retry'),path='/v1/work-packets')
        self.assertEqual(first[0],200);self.assertEqual(second[0],200)
        self.assertEqual(first[1]['result'],second[1]['result'])
        self.assertEqual(self.count('pilot_events'),1)
        with self.tx('audit_reviewer') as tx: archive=export_complete_snapshot(tx,self.custody)
        self.assertEqual(len(archive['payload']['tables']),34)

    def test_http_changed_idempotency_payload_conflicts(self):
        self.assertEqual(self.call(self.proposal())[0],200)
        altered=self.proposal();altered['payload']['event']['event_id']='syn-other-event'
        self.assertIn(self.call(altered)[0],(400,409))
        self.assertEqual(self.count('pilot_proposals'),1)

    def test_http_stale_revision_denied(self):
        data=self.proposal();data['expected_revision']=1
        self.assertEqual(self.call(data)[0],409)
        self.assertEqual(self.count('pilot_proposals'),0)

    def test_http_identity_and_tenant_denials_do_not_write(self):
        for field in ('tenant_reference','actor_reference','authentication_state_reference'):
            self.assertIn(self.call(self.proposal(**{field:'syn-forged'}))[0],(400,403))
        self.assertEqual(self.count('pilot_proposals'),0)

    def test_http_classification_immutable(self):
        data=envelope('classification.preserve',JOURNEY,{'original_classification':'syn-other'},role='data_writer',revision=0)
        self.assertEqual(self.call(data,path='/v1/classifications/preserve')[0],403)
        with self.tx() as tx:self.assertEqual(tx.read_pilot(JOURNEY)['journey']['original_classification'],'syn-entry-class')

    def test_http_command_center_uses_existing_minimized_projection(self):
        packet=self.stage()['packet_references'][0]
        data=envelope('visibility.project',packet,{'audience':'command','team_reference':None},
                      role='data_reader',correlation=self.intake.event_id)
        code,body=self.call(data,'GET','/v1/command-center',role='data_reader')
        self.assertEqual(code,200)
        self.assertFalse({'payload','facts','approval_reference','required_action'} & body['result'].keys())
        self.assertEqual(body['result']['audience'],'command')
        data['tenant_reference']='syn-tenant-2'
        code,body=self.call(data,'GET','/v1/command-center',role='data_reader')
        self.assertEqual(code,403);self.assertNotIn(packet,str(body))

    def test_http_invalid_projection_rolls_back(self):
        with patch('mission_control.connection_services.validate_projection',side_effect=ValueError('private-marker')):
            code,body=self.call(self.proposal())
        self.assertEqual(code,400);self.assertNotIn('private-marker',str(body))
        self.assertEqual(self.count('pilot_proposals'),0)

        # The HTTP deadline reaches the existing precommit budget and rolls back.
        from mission_control.pilot_postgres import PilotTransaction
        original = PilotTransaction.propose_event
        def delayed(tx, *args):
            value = original(tx, *args)
            time.sleep(0.05)
            return value
        with patch.object(PilotTransaction, 'propose_event', delayed):
            code,body=self.call(self.proposal(),timeout_seconds=0.02)
        self.assertEqual(code,408)
        self.assertEqual(self.count('pilot_proposals'),0)

    def test_http_service_failure_sanitized(self):
        with patch.object(self.audit,'append',side_effect=OSError('private-marker')):
            code,body=self.call(self.proposal())
        self.assertEqual(code,503);self.assertNotIn('private-marker',str(body))
        self.assertEqual(self.count('pilot_proposals'),0)
