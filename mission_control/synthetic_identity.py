"""Local synthetic claims and duties. Not a production identity or key service."""
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import secrets

from .contracts import text
from .registry_authorization import Principal, current_interval, positive_revision

PRIVILEGED = frozenset({'policy_admin', 'approval_issuer', 'signing_custodian',
                        'encryption_custodian', 'audit_reviewer', 'migration_operator'})
ROLE_ACTIONS = {
    'data_reader': {'registry.read', 'packet.read', 'journey.read'},
    'data_writer': {'registry.read', 'registry.append_draft', 'packet.read',
                    'packet.append_inactive', 'journey.read', 'journey.append_inactive'},
    'service_writer': {'registry.read', 'registry.append_draft', 'packet.read',
                       'packet.append_inactive', 'journey.read', 'journey.append_inactive'},
    'policy_admin': {'policy.append'},
    'approval_issuer': {'registry.read', 'approval.issue', 'approval.verify', 'approval.revoke'},
    'audit_reviewer': {'audit.read', 'backup.export'},
    'migration_operator': {'schema.migrate', 'backup.restore'},
    'signing_custodian': {'signing.manage'},
    'encryption_custodian': {'encryption.manage'},
}

# Inactive Phase 1C capabilities; each still needs an exact-resource policy grant.
ROLE_ACTIONS['data_writer'].update({'registry.department.read','registry.department.append',
    'registry.rule.read','registry.rule.append','packet.route_simulate','packet.routing.append',
    'packet.routing.read','journey.routing.read'})
ROLE_ACTIONS['service_writer'].update(ROLE_ACTIONS['data_writer'])
ROLE_ACTIONS['data_reader'].update({'packet.view.executive','packet.view.team',
    'packet.view.command','packet.view.control','packet.view.governance','packet.distribute'})
ROLE_ACTIONS['policy_admin'].add('policy.reference.append')
ROLE_ACTIONS['approval_issuer'].update({'registry.department.read','registry.rule.read',
    'approval.routing.issue','approval.routing.verify','approval.routing.revoke'})

# Phase 1D adds no operational actions. Exact grants remain mandatory.
for role in ('data_writer','service_writer'):
    ROLE_ACTIONS[role].update({'journey.pilot.start','journey.pilot.propose','journey.pilot.advance','journey.pilot.read'})
ROLE_ACTIONS['approval_issuer'].update({'approval.pilot.issue','approval.pilot.revoke'})


def synthetic_reference(value):
    text(value)
    if not value.startswith('syn-') or len(value) > 200:
        raise ValueError('Synthetic reference required')


def canonical(value):
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError('Timezone required')
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, dict):
        return {key: canonical(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [canonical(item) for item in value]
    return value


def canonical_bytes(value):
    return json.dumps(canonical(value), sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def fingerprint(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


@dataclass(frozen=True)
class SyntheticSession:
    principal: Principal
    kind: str = 'human'
    individual: bool = False
    mfa_verified: bool = False
    mfa_at: datetime | None = None

    def validate(self, tenant):
        if type(self.principal) is not Principal:
            raise PermissionError('Unverified synthetic identity')
        self.principal.validate('mission-control-registry', tenant)
        for value in (tenant, self.principal.subject_reference):
            synthetic_reference(value)
        roles = set(self.principal.roles)
        if not roles <= ROLE_ACTIONS.keys() or len(roles & PRIVILEGED) > 1:
            raise PermissionError('Separation of duties violation')
        if self.kind == 'human':
            if self.individual is not True or self.mfa_verified is not True:
                raise PermissionError('Individual MFA identity required')
            if not isinstance(self.mfa_at, datetime) or not current_interval(
                    self.mfa_at, self.mfa_at + timedelta(minutes=5)):
                raise PermissionError('Fresh synthetic MFA required')
        elif self.kind == 'service':
            if roles - {'service_writer', 'data_reader'} or self.mfa_verified is not False:
                raise PermissionError('Service privilege escalation')
            if self.principal.expires_at - self.principal.valid_from > timedelta(minutes=15):
                raise PermissionError('Service credential lifetime exceeds synthetic bound')
        else:
            raise PermissionError('Unknown identity kind')


@dataclass(frozen=True)
class SyntheticGrant:
    role: str
    action: str
    resource: str
    effect: str = 'deny'
    subject_reference: str | None = None


@dataclass(frozen=True)
class SyntheticPolicy:
    tenant: str
    revision: int
    grants: tuple[SyntheticGrant, ...]
    valid_from: datetime
    expires_at: datetime

    def validate(self, tenant, revision):
        synthetic_reference(self.tenant)
        positive_revision(self.revision)
        positive_revision(revision)
        if self.tenant != tenant or self.revision != revision or not current_interval(self.valid_from, self.expires_at):
            raise PermissionError('Stale or mismatched synthetic policy')
        if not isinstance(self.grants, tuple):
            raise PermissionError('Malformed policy')
        for grant in self.grants:
            if type(grant) is not SyntheticGrant or grant.role not in ROLE_ACTIONS:
                raise PermissionError('Unknown grant')
            synthetic_reference(grant.resource)
            if grant.subject_reference is not None:
                synthetic_reference(grant.subject_reference)
            if grant.action not in ROLE_ACTIONS[grant.role] or grant.effect not in ('allow', 'deny'):
                raise PermissionError('Unsupported grant')


class SyntheticAuthority:
    """Trusted test fixture, not caller-provided authentication claims."""
    def __init__(self, sessions=None, policies=None):
        self.sessions = dict(sessions or {})
        self.policies = dict(policies or {})

    def resolve(self, session_reference, tenant, revision):
        try:
            synthetic_reference(session_reference)
            session = self.sessions.get(session_reference)
            policy = self.policies.get(tenant)
            if type(session) is not SyntheticSession or type(policy) is not SyntheticPolicy:
                raise ValueError('Unavailable authority')
            session.validate(tenant)
            # Multiple sessions for one subject cannot split conflicting duties.
            duties = set()
            for candidate in self.sessions.values():
                if (type(candidate) is SyntheticSession and type(candidate.principal) is Principal
                        and candidate.principal.subject_reference == session.principal.subject_reference
                        and candidate.principal.tenant_reference == tenant
                        and candidate.principal.revoked is False
                        and current_interval(candidate.principal.valid_from,candidate.principal.expires_at)):
                    duties.update(set(candidate.principal.roles) & PRIVILEGED)
            if len(duties) > 1:
                raise PermissionError('Conflicting duties across sessions')
            policy.validate(tenant, revision)
            return session, policy
        except Exception:
            raise PermissionError('Synthetic identity or policy verification failed') from None

    def authorize(self, session_reference, tenant, revision, action, resource):
        session, policy = self.resolve(session_reference, tenant, revision)
        synthetic_reference(resource)
        matching = [grant for grant in policy.grants if grant.role in session.principal.roles
                    and grant.action == action and grant.resource == resource
                    and grant.subject_reference in (None, session.principal.subject_reference)]
        if not matching or any(grant.effect == 'deny' for grant in matching):
            raise PermissionError('Synthetic permission denied')
        return session, policy


class SyntheticEvidenceCustody:
    """Ephemeral HMAC for local tests only; not production signatures/nonrepudiation.

    Encryption custody cannot initialize signing custody. Key material is never
    included in evidence or exports. A fresh custody cannot verify older proofs.
    """
    def __init__(self, authority, session_reference, tenant, revision):
        authority.authorize(session_reference, tenant, revision, 'signing.manage', 'syn-signing-key')
        self._key = secrets.token_bytes(32)
        self.key_reference = 'syn-key-' + secrets.token_hex(8)

    def seal(self, payload):
        return {'key_reference': self.key_reference,
                'mac': hmac.new(self._key, canonical_bytes(payload), hashlib.sha256).hexdigest()}

    def verify(self, payload, proof):
        if not isinstance(proof, dict) or set(proof) != {'key_reference', 'mac'}:
            return False
        if proof['key_reference'] != self.key_reference or not isinstance(proof['mac'], str):
            return False
        return hmac.compare_digest(self.seal(payload)['mac'], proof['mac'])
