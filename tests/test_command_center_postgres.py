"""UI-confirmed intake through existing gateway and disposable PostgreSQL only."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import json
import time
import unittest
from unittest.mock import patch

from mission_control.command_center_ui import UIConfig,ROOT
from mission_control.connection_services import PhaseOneServices
from mission_control.pilot_postgres import PilotTransaction
from tests import test_postgres_integration as base_pg
from tests.pilot_pg_support import PilotFixture
from tests.pilot_support import TENANT,JOURNEY
from tests.command_center_support import running_ui,session,ui_request
from tests.connection_support import gateway_fixture,envelope,encoded
from tests.test_command_center_ui import prepared,confirmed


@unittest.skipUnless(base_pg.AVAILABLE,base_pg.REASON)
class CommandCenterPostgreSQLTests(PilotFixture,unittest.TestCase):
    def setUp(self):
        PilotFixture.setUp(self)
        self.store,self.admin=self.new_empty_store()
        with self.tx('policy_admin') as tx:
            tx.bootstrap_policy();tx.register_reference('classification','syn-entry-class');tx.commit()
        self.gateway,_,self.audit=gateway_fixture(self.authority,PhaseOneServices(self.store))
        self.config=UIConfig(reads=(encoded(envelope('journey.read',JOURNEY,role='data_writer',revision=0)),),actions=(encoded(envelope('intake',JOURNEY,{'journey':asdict(self.journey),'intake':asdict(self.intake)},role='data_writer',revision=0)),))

    def test_confirmed_intake_preserves_classification_and_history(self):
        with running_ui(self.gateway,self.config,'data_writer') as (server,_):
            cookie,overview=session(server);self.assertEqual(overview['items'],[])
            code,_,value=prepared(server,cookie,overview);self.assertEqual(code,200)
            self.assertEqual(ui_request(server,ROOT+'/api/confirm','POST',confirmed(value),cookie)[0],200)
            code,_,view=ui_request(server,ROOT+'/api/overview',cookie=cookie)
            result=view['items'][0]['projection']
            self.assertEqual(result['original_classification'],'syn-entry-class');self.assertEqual(result['events'],[])
            self.assertEqual(ui_request(server,ROOT+'/api/confirm','POST',confirmed(value),cookie)[0],409)
            self.assertEqual(self.count('pilot_journeys'),1);self.assertEqual(self.count('pilot_events'),0)
            self.assertNotIn('guest_reference',str(view));self.assertNotIn('payload',str(view))

    def test_no_confirmation_or_bad_csrf_never_writes(self):
        with running_ui(self.gateway,self.config,'data_writer') as (server,_):
            cookie,overview=session(server);_,_,value=prepared(server,cookie,overview)
            for changes in ({'confirmed':False},{'csrf_token':'forged'},{'expected_revision':1}):
                self.assertIn(ui_request(server,ROOT+'/api/confirm','POST',confirmed(value,**changes),cookie)[0],(403,409))
            self.assertEqual(self.count('pilot_journeys'),0)

    def test_transaction_invalid_output_rollback(self):
        with running_ui(self.gateway,self.config,'data_writer') as (server,_):
            cookie,overview=session(server);_,_,value=prepared(server,cookie,overview)
            with patch('mission_control.connection_services.validate_projection',side_effect=ValueError('private-marker')):
                code,_,body=ui_request(server,ROOT+'/api/confirm','POST',confirmed(value),cookie)
            self.assertEqual(code,400);self.assertEqual(self.count('pilot_journeys'),0)
            self.assertNotIn('private-marker',str(body))

    def test_cooperative_timeout_rolls_back(self):
        original=PilotTransaction.start_journey
        def delayed(tx,*args):
            result=original(tx,*args);time.sleep(0.05);return result
        with running_ui(self.gateway,self.config,'data_writer') as (server,_):
            cookie,overview=session(server);_,_,value=prepared(server,cookie,overview)
            server.timeout_seconds=0.02  # Bound the operation under test, not fixture preparation.
            with patch.object(PilotTransaction,'start_journey',delayed):
                code,_,_=ui_request(server,ROOT+'/api/confirm','POST',confirmed(value),cookie)
            self.assertEqual(code,408);self.assertEqual(self.count('pilot_journeys'),0)

    def test_concurrent_confirmation_one_domain_write(self):
        with running_ui(self.gateway,self.config,'data_writer') as (server,_):
            cookie,overview=session(server);_,_,value=prepared(server,cookie,overview)
            with ThreadPoolExecutor(max_workers=2) as pool:
                results=list(pool.map(lambda _:ui_request(server,ROOT+'/api/confirm','POST',confirmed(value),cookie)[0],range(2)))
            self.assertEqual(sorted(results),[200,409]);self.assertEqual(self.count('pilot_journeys'),1)

    def test_fresh_confirmation_after_success_reuses_domain_idempotency(self):
        with running_ui(self.gateway,self.config,'data_writer') as (server,_):
            cookie,overview=session(server);_,_,value=prepared(server,cookie,overview)
            self.assertEqual(ui_request(server,ROOT+'/api/confirm','POST',confirmed(value),cookie)[0],200)
            # The same authorized envelope/key at the unchanged gateway is idempotent.
            intent=next(iter(server.sessions.values()))['intents']['syn-ui-action-1']
            self.assertEqual(server.call(intent['raw'])[0],200)
            self.assertEqual(self.count('pilot_journeys'),1)

    def test_tenant_and_idor_denials_do_not_reveal_references(self):
        with self.tx() as tx:tx.start_journey(self.journey,self.intake,'syn-start');tx.commit()
        request=envelope('journey.read','syn-missing-journey',role='data_writer',revision=0,correlation='syn-missing-journey')
        # Existing gateway rejects unauthorized candidates even before UI listener creation.
        with self.assertRaises(PermissionError):
            with running_ui(self.gateway,UIConfig(reads=(encoded(request),)),'data_writer'):pass
        request=envelope('journey.read',JOURNEY,role='data_writer',tenant='syn-tenant-2',revision=0)
        with self.assertRaises(PermissionError):
            with running_ui(self.gateway,UIConfig(reads=(encoded(request),)),'data_writer'):pass

    def test_original_history_is_append_only_and_not_edited_by_view(self):
        # Existing seeded store has accepted events; UI reads cannot rewrite them.
        PilotFixture.setUp(self);self.stage()
        gateway,_,_=gateway_fixture(self.authority,PhaseOneServices(self.store))
        config=UIConfig(reads=(encoded(envelope('journey.read',JOURNEY,role='data_writer',revision=1)),))
        with self.tx() as tx:before=tx.read_pilot(JOURNEY)
        with running_ui(gateway,config,'data_writer') as (server,_):
            cookie,overview=session(server)
            self.assertEqual(len(overview['items'][0]['projection']['events']),1)
            ui_request(server,ROOT+'/api/overview',cookie=cookie)
        with self.tx() as tx:after=tx.read_pilot(JOURNEY)
        self.assertEqual(before,after)
