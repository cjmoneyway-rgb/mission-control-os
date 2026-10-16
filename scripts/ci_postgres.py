"""GitHub-hosted, disposable-service verification only. Never a cloud DSN runner."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def job_context():
    if (os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('MC_SYN_CI_POSTGRES') != '1'
            or os.environ.get('RUNNER_ENVIRONMENT') != 'github-hosted'
            or os.environ.get('RUNNER_OS') != 'Linux'):
        raise RuntimeError('Requires the explicit GitHub-hosted synthetic verification job')
    root = Path(os.environ['RUNNER_TEMP']).resolve()
    if not root.is_dir():
        raise RuntimeError('Job temporary directory unavailable')
    return root / 'mc-syn-postgres-credentials.json'


def credentials():
    path = job_context()
    if path.is_symlink() or (path.stat().st_mode & 0o777) != 0o600:
        raise RuntimeError('Unsafe synthetic credential file')
    from mission_control.json_io import strict_json_loads
    value = strict_json_loads(path.read_text())
    if (not isinstance(value,dict) or set(value) != {'admin_password','runtime_password'}
            or any(not isinstance(item,str) or len(item)<40 for item in value.values())):
        raise RuntimeError('Malformed job credentials')
    return value


def service_connection(database,user,autocommit=False):
    import psycopg
    from mission_control.synthetic_identity import synthetic_reference
    if database != 'postgres':
        synthetic_reference(database)
    if user not in ('syn-admin','syn-runtime'):
        raise ValueError('Unsupported disposable-service identity')
    values = credentials()
    return psycopg.connect(host='127.0.0.1',port=5432,dbname=database,user=user,
        password=values['admin_password' if user=='syn-admin' else 'runtime_password'],
        connect_timeout=3,autocommit=autocommit,sslmode='disable')


def bootstrap():
    import psycopg
    from psycopg import sql
    path = job_context()
    container = os.environ['MC_SYN_POSTGRES_CONTAINER']
    if not container or any(char not in '0123456789abcdef' for char in container):
        raise RuntimeError('Invalid job-owned container identity')
    values = {'admin_password':secrets.token_urlsafe(40),'runtime_password':secrets.token_urlsafe(40)}
    for value in values.values():
        print('::add-mask::'+value,flush=True)
    fd = os.open(path,os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as handle:
        json.dump(values,handle)
    with psycopg.connect(host='127.0.0.1',port=5432,dbname='postgres',user='postgres',connect_timeout=3,autocommit=True) as connection:
        connection.execute("SET password_encryption = 'scram-sha-256'")
        connection.execute(sql.SQL('CREATE ROLE {} LOGIN SUPERUSER PASSWORD {}').format(
            sql.Identifier('syn-admin'),sql.Literal(values['admin_password'])))
        connection.execute('ALTER ROLE postgres NOLOGIN')
        subprocess.run(['docker','exec',container,'sh','-c',
            'printf "%s\\n" "local all all trust" "host all all all scram-sha-256" > "$PGDATA/pg_hba.conf"'],check=True)
        connection.execute('SELECT pg_reload_conf()')
    # Confirm host trust is actually gone before allowing any test connection.
    for _ in range(30):
        try:
            probe = psycopg.connect(host='127.0.0.1',port=5432,dbname='postgres',user='syn-admin',password='deliberately-invalid',connect_timeout=2)
        except psycopg.OperationalError:
            break
        else:
            probe.close()
            time.sleep(0.1)
    else:
        raise RuntimeError('Disposable service still accepts unauthenticated host access')
    with service_connection('postgres','syn-admin',autocommit=True) as connection:
        number,version = connection.execute("SELECT current_setting('server_version_num')::int,version()").fetchone()
        if number != 170011:
            raise RuntimeError('PostgreSQL version differs from reviewed image')
    print('Disposable PostgreSQL version: '+version)
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary,'a') as handle:
            handle.write('### Disposable PostgreSQL\n\n'+version+'\n\n')


def flatten(suite):
    for item in suite:
        if isinstance(item,unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


class ExecutedResult(unittest.TextTestResult):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.executed_ids = []
    def startTest(self,test):
        self.executed_ids.append(test.id())
        super().startTest(test)


def verify():
    job_context()
    os.chdir(ROOT)
    suite = unittest.defaultTestLoader.discover('tests',top_level_dir='.')
    ids = [test.id() for test in flatten(suite)]
    groups = {'tests.test_postgres_integration.PostgreSQLIntegrationTests.': 10,
              'tests.test_routing_postgres.RoutingPostgreSQLTests.': 43,
              'tests.test_pilot_postgres.PilotPostgreSQLTests.': 33,
              'tests.test_pilot_archive_postgres.PilotArchivePostgreSQLTests.': 16}
    pg_ids = {identifier for identifier in ids if identifier.startswith(tuple(groups))}
    if len(ids) != 227 or any(sum(identifier.startswith(prefix) for identifier in ids) != count
                             for prefix,count in groups.items()):
        raise RuntimeError('Expected exactly 227 tests including 102 PostgreSQL tests')
    result = unittest.TextTestRunner(verbosity=2,resultclass=ExecutedResult).run(suite)
    counts = {'discovered':len(ids),'executed':result.testsRun,
              'postgresql_executed':len(pg_ids & set(result.executed_ids)),
              'failures':len(result.failures),'errors':len(result.errors),'skips':len(result.skipped),
              'expected_failures':len(result.expectedFailures),'unexpected_successes':len(result.unexpectedSuccesses)}
    print('VERIFICATION_COUNTS '+json.dumps(counts,sort_keys=True))
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary,'a') as handle:
            handle.write('### Synthetic test results\n\n```json\n'+json.dumps(counts,indent=2)+'\n```\n')
    if (not result.wasSuccessful() or result.testsRun != 227 or counts['postgresql_executed'] != 102
            or result.skipped or result.expectedFailures or result.unexpectedSuccesses):
        raise SystemExit(1)


if __name__ == '__main__':
    if len(sys.argv) != 2 or sys.argv[1] not in ('bootstrap','verify'):
        raise SystemExit('Use bootstrap or verify inside the manual CI job')
    globals()[sys.argv[1]]()
