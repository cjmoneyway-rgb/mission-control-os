"""Run all tests on the reviewed disposable PG 17.11 image, without TCP or CI spoofing.

Requires Docker and an already downloaded, digest-pinned official image. No cloud
DSN, credential, deployment, daemon installation, or repository mutation occurs.
"""
import os
import json
import unittest
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid

IMAGE = 'postgres:17.11-bookworm@sha256:3645570cccdfa447589da9f57dd740faa29b30938e861289a5574b6ca6b03826'
ROOT = Path(__file__).resolve().parents[1]


def main():
    if os.name != 'posix' or os.geteuid() == 0 or os.environ.get('MC_SYN_CI_POSTGRES'):
        raise RuntimeError('Requires non-root POSIX local synthetic test context')
    subprocess.run(['docker','image','inspect',IMAGE],check=True,stdout=subprocess.DEVNULL)
    name = 'mc-syn-phase2b-' + uuid.uuid4().hex
    with tempfile.TemporaryDirectory(prefix='mc-syn-tools-',dir='/tmp') as directory:
        try:
            subprocess.run(['docker','run','-d','--rm','--name',name,'--network','none',
                '--user',f'{os.getuid()}:{os.getgid()}',
                '--mount','type=bind,src=/tmp,dst=/tmp',
                '--mount','type=bind,src=/etc/passwd,dst=/etc/passwd,readonly',
                '--entrypoint','/bin/sleep',IMAGE,'infinity'],check=True,stdout=subprocess.DEVNULL)
            subprocess.run(['docker','exec',name,'/usr/lib/postgresql/17/bin/postgres','--version'],check=True)
            for binary in ('initdb','pg_ctl'):
                wrapper = Path(directory)/binary
                extra = ' --encoding=UTF8' if binary == 'initdb' else ''
                wrapper.write_text('#!/bin/sh\nexec docker exec '+name+
                    ' /usr/lib/postgresql/17/bin/'+binary+extra+' "$@"\n')
                wrapper.chmod(0o700)
            environment = dict(os.environ,PATH=directory+os.pathsep+os.environ['PATH'],
                               PYTHONDONTWRITEBYTECODE='1')
            return subprocess.run([sys.executable,'-B',str(Path(__file__).resolve()),'--execute'],
                                  cwd=ROOT,env=environment).returncode
        finally:
            subprocess.run(['docker','rm','-f',name],check=False,stdout=subprocess.DEVNULL)


def verify():
    sys.path.insert(0,str(ROOT))
    from scripts.ci_postgres import flatten, ExecutedResult
    suite = unittest.defaultTestLoader.discover('tests',top_level_dir='.')
    ids = {test.id() for test in flatten(suite)}
    pg = {identifier for identifier in ids if '_postgres.' in identifier or
          'test_postgres_integration.' in identifier}
    if len(ids) != 373 or len(pg) != 167:
        raise RuntimeError('Expected 373 tests including 167 PostgreSQL tests')
    result = unittest.TextTestRunner(verbosity=2,resultclass=ExecutedResult).run(suite)
    counts = dict(discovered=len(ids),executed=result.testsRun,
        postgresql_executed=len(pg & set(result.executed_ids)),failures=len(result.failures),
        errors=len(result.errors),skips=len(result.skipped),
        expected_failures=len(result.expectedFailures),unexpected_successes=len(result.unexpectedSuccesses))
    print('VERIFICATION_COUNTS '+json.dumps(counts,sort_keys=True))
    return int(not result.wasSuccessful() or result.testsRun != len(ids) or
               bool(result.skipped or result.expectedFailures or result.unexpectedSuccesses))


if __name__ == '__main__':
    raise SystemExit(verify() if sys.argv[1:] == ['--execute'] else main())
