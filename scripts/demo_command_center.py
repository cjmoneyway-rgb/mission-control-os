"""Temporary synthetic CEO UI demo; no external network, persistent listener or tokens printed."""
import argparse
from dataclasses import asdict
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def worker(browser_check=False):
    from mission_control.command_center_ui import UIConfig,ROOT as UI_ROOT
    from mission_control.connection_services import PhaseOneServices
    from mission_control.connection_contracts import COMMAND_STAGES,CONNECTORS
    from tests.command_center_support import running_ui,session,ui_request
    from tests.connection_support import envelope,encoded,gateway_fixture
    from tests.pilot_pg_support import PilotFixture
    from tests.pilot_support import JOURNEY
    from tests.test_command_center_ui import prepared,confirmed
    class Fixture(PilotFixture):pass
    Fixture.setUpClass()
    try:
        fixture=Fixture();fixture.setUp()
        fixture.store,fixture.admin=fixture.new_empty_store()
        with fixture.tx('policy_admin') as tx:
            tx.bootstrap_policy();tx.register_reference('classification','syn-entry-class');tx.commit()
        gateway,_,_=gateway_fixture(fixture.authority,PhaseOneServices(fixture.store))
        config=UIConfig(reads=(encoded(envelope('journey.read',JOURNEY,role='data_writer',revision=0)),),actions=(
            encoded(envelope('intake',JOURNEY,{'journey':asdict(fixture.journey),'intake':asdict(fixture.intake)},role='data_writer',revision=0)),
            encoded(envelope('decision.submit',JOURNEY,{'event':asdict(fixture.events[0])},role='data_writer',revision=0))))
        with running_ui(gateway,config,'data_writer') as (server,_):
            if browser_check:
                origin=f'http://127.0.0.1:{server.server_address[1]}'
                subprocess.run(['node',str(ROOT/'scripts/verify_command_center_browser.js'),origin],check=True)
            else:
                cookie,overview=session(server)
                assert overview['stages']==list(COMMAND_STAGES)
                code,_,confirmation=prepared(server,cookie,overview);assert code==200
                assert ui_request(server,UI_ROOT+'/api/confirm','POST',confirmed(confirmation,confirmed=False),cookie)[0]==403
                assert ui_request(server,UI_ROOT+'/api/confirm','POST',confirmed(confirmation),cookie)[0]==200
                assert ui_request(server,UI_ROOT+'/api/confirm','POST',confirmed(confirmation),cookie)[0]==409
                body={'action_reference':'syn-ui-action-2','csrf_token':overview['csrf_token']}
                assert ui_request(server,UI_ROOT+'/api/prepare','POST',body,cookie)[0] in (400,403,409)
            assert fixture.count('pilot_journeys')==1
            assert len(CONNECTORS)==7 and all(not item.enabled for item in CONNECTORS)
        assert not server.sessions
        print('PASS: executive overview, six ordered stages, confirmation-gated synthetic intake, blocked/replayed action, seven disabled connectors, listener stopped.')
    finally:
        Fixture.tearDownClass()
        print('Disposable database and temporary fixture files removed; no credentials saved.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--synthetic-development',action='store_true',required=True)
    parser.add_argument('--browser-check',action='store_true')
    parser.add_argument('--worker',action='store_true',help=argparse.SUPPRESS)
    options=parser.parse_args()
    if options.worker:worker(options.browser_check);return 0
    from scripts.local_postgres_tests import main as disposable
    command=[sys.executable,'-B',str(Path(__file__).resolve()),'--synthetic-development','--worker']
    if options.browser_check:command.append('--browser-check')
    return disposable(command)


if __name__=='__main__':raise SystemExit(main())
