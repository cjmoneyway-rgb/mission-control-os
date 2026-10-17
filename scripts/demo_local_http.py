"""Explicit ephemeral synthetic demonstration; no database, log, or external client.

Domain behavior is not simulated: only gateway health and denial are demonstrated.
The persistence and Command Center proofs live in the PostgreSQL socket tests.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tests.connection_support import envelope, gateway_fixture
from tests.local_http_support import running, request


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--synthetic-development',action='store_true',required=True)
    parser.parse_args()
    gateway,_,_=gateway_fixture()
    with running(gateway) as (server,binding):
        code,_,raw=request(server,binding,envelope())
        assert code == 200 and json.loads(raw)['result'] == {'state':'inactive'}
        code,_,_=request(server,binding,envelope(actor_reference='syn-forged'))
        assert code == 403
    print('Synthetic loopback health: PASS; forged identity: DENIED; listener: STOPPED')
    print('Seven connectors disabled; no operational authorization or outbound transport.')


if __name__ == '__main__':
    main()
