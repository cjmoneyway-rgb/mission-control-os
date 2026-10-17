"""Exact governed contracts; no protected facts in the schema or browser authority."""
from copy import deepcopy
from datetime import datetime,timezone
import unittest
from unittest.mock import patch

from mission_control.connection_contracts import (COMMAND_STAGES,COMMAND_ITEM_FIELDS,validate_command_center,validate_eligibility)
from tests.connection_support import envelope,gateway_fixture
from tests.test_command_center_ui import intake_config,prepared,confirmed
from tests.command_center_support import running_ui,session,ui_request
from mission_control.command_center_ui import ROOT


class GovernedContractTests(unittest.TestCase):
    def projection(self):return dict(schema_revision=1,state='inactive',queues=[dict(stage=stage,count=0,blocked_count=0,items=[]) for stage in COMMAND_STAGES])

    def test_exact_six_stage_order_and_counts(self):
        value=self.projection();validate_command_center(value)
        value['queues'].reverse()
        with self.assertRaises(ValueError):validate_command_center(value)

    def test_hidden_counts_extra_fields_and_noninteger_counts_rejected(self):
        for change in ({'count':True},{'count':1},{'blocked_count':1},{'hidden_count':2}):
            value=self.projection();value['queues'][0].update(change)
            with self.assertRaises(ValueError):validate_command_center(value)

    def test_eligibility_exact_minimized_fresh_and_bound(self):
        value=dict(target_reference='syn-target',requested_action='intake',eligible=False,blocker_codes=['unresolved_dependencies'],expected_revision=0,evaluated_at=datetime.now(timezone.utc).isoformat(),schema_revision=1)
        validate_eligibility(value)
        for change in ({'eligible':True},{'policy':'syn-private'},{'blocker_codes':['private-message']},{'evaluated_at':'2000-01-01T00:00:00+00:00'},{'expected_revision':True}):
            with self.subTest(change=change),self.assertRaises(ValueError):validate_eligibility(dict(value,**change))

    def test_missing_eligibility_and_browser_override_fail_closed(self):
        gateway,services,_=gateway_fixture()
        with running_ui(gateway,intake_config(),'data_writer') as (server,_):
            cookie,overview=session(server)
            with patch.object(services,'eligibility',return_value=None):
                self.assertEqual(prepared(server,cookie,overview)[0],400)
            body={'action_reference':'syn-ui-action-1','csrf_token':overview['csrf_token'],'eligibility':True}
            self.assertEqual(ui_request(server,ROOT+'/api/prepare','POST',body,cookie)[0],400)
            self.assertEqual(services.calls,[])

    def test_stale_displayed_eligibility_is_not_authority(self):
        gateway,services,_=gateway_fixture()
        with running_ui(gateway,intake_config(),'data_writer') as (server,_):
            cookie,overview=session(server);code,_,confirmation=prepared(server,cookie,overview);self.assertEqual(code,200)
            original=services.eligibility
            def denied(*args):
                value=original(*args);value.update(eligible=False,blocker_codes=['stale_revision']);return value
            with patch.object(services,'eligibility',side_effect=denied):
                self.assertEqual(ui_request(server,ROOT+'/api/confirm','POST',confirmed(confirmation),cookie)[0],409)
            self.assertEqual(services.calls,[])

    def test_malformed_governed_projection_fails_without_legacy_fallback(self):
        gateway,services,_=gateway_fixture()
        with running_ui(gateway,intake_config(),'data_writer') as (server,_):
            cookie,overview=session(server)
            with patch.object(services,'command_center',return_value={'state':'inactive','hidden':1}):
                self.assertEqual(ui_request(server,ROOT+'/api/overview',cookie=cookie)[0],400)

    def test_governed_query_retains_rate_admission(self):
        from mission_control.connection_gateway import LocalRateLimit
        gateway,_,_=gateway_fixture()
        with running_ui(gateway,intake_config(),'data_writer') as (server,_):
            cookie,overview=session(server)
            gateway.rate_limit=LocalRateLimit(1)
            self.assertEqual(ui_request(server,ROOT+'/api/overview',cookie=cookie)[0],429)

    def test_governed_admission_audit_failure_precedes_database_work(self):
        gateway,services,audit=gateway_fixture()
        with running_ui(gateway,intake_config(),'data_writer') as (server,_):
            cookie,overview=session(server)
            with patch.object(audit,'append',side_effect=RuntimeError('private-marker')),patch.object(services,'command_center',side_effect=AssertionError('No domain query')):
                code,_,body=ui_request(server,ROOT+'/api/overview',cookie=cookie)
            self.assertEqual(code,503);self.assertNotIn('private-marker',str(body))
