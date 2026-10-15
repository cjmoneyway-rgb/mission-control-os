"""Minimized append-only audit; retention creates a separate, non-destructive view."""
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
import stat
import tempfile

from .json_io import strict_json_loads


class JsonlAuditLog:
    def __init__(self, path, retention_days=None, include_route=False):
        self.path = Path(path).absolute()
        if retention_days is not None and (type(retention_days) is not int or retention_days < 1):
            raise ValueError('Retention must be a positive number of days or None')
        self.retention_days = retention_days
        self.include_route = include_route

    @property
    def retained_path(self):
        return self.path.with_name(self.path.name + '.retained.jsonl')

    @contextmanager
    def _locked(self):
        # Stable sidecar, never the inode replaced by maintenance. All cooperating
        # processes/threads use this lock. Unsupported platforms fail closed.
        import fcntl
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.parent.resolve() != self.path.parent or self.path.is_symlink():
            raise ValueError('Audit paths must not use symlinks')
        lock_path = self.path.with_name(self.path.name + '.lock')
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ValueError('Audit lock must be a regular file')
            fcntl.flock(fd, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

    def append(self, record):
        payload = {
            'execution_id': record.execution_id,
            'created_at': record.created_at,
            'status': 'validated' if record.governance.passed else 'blocked',
            'authorization': 'not_granted_by_technical_validation',
            'revision_count': record.revision_count,
            'schema_revision': 1,
            'finding_count': len(record.governance.findings),
        }
        if self.include_route:
            payload['route'] = {'department_id': record.route.department_id}
        encoded = (json.dumps(payload, allow_nan=False) + '\n').encode('utf-8')
        with self._locked():
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'ab') as handle:
                if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                    raise ValueError('Audit destination must be a regular file')
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())

    def purge_expired(self):
        """Refresh a retention VIEW; never delete or replace source audit records.

        The returned counts describe a locked snapshot, not later appends. No
        configured retention means no operation. Historical method name retained
        for compatibility; this operation deliberately does not reclaim storage.
        """
        if self.retention_days is None:
            return None
        with self._locked():
            if not self.path.exists():
                return None
            if not stat.S_ISREG(self.path.stat().st_mode):
                raise ValueError('Audit source must be a regular file')
            source = self.path.read_bytes()
            lines = source.splitlines(keepends=True)
            cutoff = datetime.now(timezone.utc) - timedelta(days=self.retention_days)
            retained = []
            # Never copy raw legacy records into a new view. Refuse unknown fields
            # rather than quietly redacting/migrating historical audit evidence.
            required = {'execution_id', 'created_at', 'status', 'authorization',
                        'revision_count', 'schema_revision', 'finding_count'}
            for line in lines:
                try:
                    payload = strict_json_loads(line)
                    if (not isinstance(payload, dict) or not required <= set(payload)
                            or set(payload) - required - {'route'}
                            or type(payload['schema_revision']) is not int
                            or payload['schema_revision'] != 1):
                        raise ValueError('Legacy or unknown audit schema')
                    timestamp = datetime.fromisoformat(payload['created_at'])
                    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
                        raise ValueError('Audit timestamps require a timezone')
                except (ValueError, KeyError, TypeError):
                    raise ValueError('Invalid or legacy audit record requires separate review') from None
                if timestamp >= cutoff:
                    retained.append(line)
            return self._publish_view(b''.join(retained), len(lines), len(retained))

    def _publish_view(self, data, source_count, retained_count):
        temporary = None
        try:
            fd, name = tempfile.mkstemp(prefix=self.path.name + '.retention-', dir=self.path.parent)
            temporary = Path(name)
            with os.fdopen(fd, 'wb') as handle:
                # Never broaden source access; mkstemp is already owner-only.
                os.fchmod(handle.fileno(), stat.S_IMODE(self.path.stat().st_mode) & 0o600)
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.retained_path)
            directory_fd = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            return {'source_count': source_count, 'retained_count': retained_count,
                    'expired_count': source_count - retained_count,
                    'view_path': str(self.retained_path)}
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
