"""Storage/identity-provider independent authorization for inactive synthetic work.

Trusted adapters must resolve sessions and policy; callers cannot submit claims
or permission rules as request data. This module is not wired into the CLI.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from .contracts import text


INACTIVE_ACTIONS = frozenset({'registry.read', 'registry.append_draft',
                              'packet.read', 'packet.append_inactive',
                              'journey.read', 'journey.append_inactive'})


def positive_revision(value):
    if type(value) is not int or value < 1:
        raise ValueError('Expected a positive integer revision')


def current_interval(start, end):
    for value in (start, end):
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError('Validity requires timezone-aware timestamps')
    return start <= datetime.now(timezone.utc) < end


@dataclass(frozen=True)
class Principal:
    subject_reference: str
    tenant_reference: str
    audience: str
    roles: tuple[str, ...]
    valid_from: datetime
    expires_at: datetime
    revoked: bool = True

    def validate(self, audience, tenant):
        for value in (self.subject_reference, self.tenant_reference, self.audience):
            text(value)
        if self.audience != audience or self.tenant_reference != tenant or self.revoked is not False:
            raise ValueError('Identity scope or revocation mismatch')
        if not isinstance(self.roles, tuple) or not self.roles or len(set(self.roles)) != len(self.roles):
            raise ValueError('Invalid role claims')
        for role in self.roles:
            text(role)
        if not current_interval(self.valid_from, self.expires_at):
            raise ValueError('Identity is expired or not yet valid')


@dataclass(frozen=True)
class PermissionRule:
    role: str
    action: str
    resource_reference: str
    effect: str = 'deny'

    def validate(self):
        for value in (self.role, self.action, self.resource_reference):
            text(value)
        if self.action not in INACTIVE_ACTIONS or self.effect not in ('allow', 'deny'):
            raise ValueError('Unsupported permission rule')
        if '*' in self.resource_reference:
            raise ValueError('Wildcard resource grants are disabled')


@dataclass(frozen=True)
class PolicySnapshot:
    tenant_reference: str
    revision: int
    rules: tuple[PermissionRule, ...]
    valid_from: datetime
    expires_at: datetime

    def validate(self, tenant, revision):
        text(self.tenant_reference)
        positive_revision(self.revision)
        if self.tenant_reference != tenant or self.revision != revision:
            raise ValueError('Policy scope or revision mismatch')
        if not current_interval(self.valid_from, self.expires_at):
            raise ValueError('Policy is expired or not yet valid')
        if not isinstance(self.rules, tuple):
            raise ValueError('Policy rules must be immutable')
        for rule in self.rules:
            if not isinstance(rule, PermissionRule):
                raise ValueError('Malformed policy rule')
            rule.validate()


class IdentityVerifier(Protocol):
    def resolve_session(self, session_reference: str) -> Principal | None: ...


class PolicyAuthority(Protocol):
    def resolve_policy(self, tenant_reference: str) -> PolicySnapshot | None: ...


@dataclass(frozen=True)
class AccessRequest:
    session_reference: str
    tenant_reference: str
    action: str
    resource_reference: str
    policy_revision: int
    dataset: str = 'synthetic'


@dataclass(frozen=True)
class AccessDecision:
    allowed: bool = False
    reason_code: str = 'denied'
    subject_reference: str | None = None
    policy_revision: int | None = None


class RegistryAuthorization:
    """Default-deny evaluator; trusted dependencies are installed by application code."""
    def __init__(self, identity: IdentityVerifier | None = None,
                 policies: PolicyAuthority | None = None,
                 audience='mission-control-registry'):
        text(audience)
        self.identity = identity
        self.policies = policies
        self.audience = audience

    def check(self, request: AccessRequest) -> AccessDecision:
        try:
            if not isinstance(request, AccessRequest):
                raise ValueError('Malformed request')
            for value in (request.session_reference, request.tenant_reference,
                          request.action, request.resource_reference):
                text(value)
            positive_revision(request.policy_revision)
            # Activation, external use, operational routing, and approvals are not
            # grantable by these synthetic permissions, even with a matching role.
            if request.dataset != 'synthetic' or request.action not in INACTIVE_ACTIONS:
                return AccessDecision(reason_code='inactive_scope_only')
            if self.identity is None or self.policies is None:
                return AccessDecision(reason_code='authority_unavailable')
            principal = self.identity.resolve_session(request.session_reference)
            policy = self.policies.resolve_policy(request.tenant_reference)
            if not isinstance(principal, Principal) or not isinstance(policy, PolicySnapshot):
                return AccessDecision(reason_code='unverified_authority_result')
            principal.validate(self.audience, request.tenant_reference)
            policy.validate(request.tenant_reference, request.policy_revision)
            matching = [rule for rule in policy.rules
                        if rule.role in principal.roles and rule.action == request.action
                        and rule.resource_reference == request.resource_reference]
            if not matching or any(rule.effect == 'deny' for rule in matching):
                return AccessDecision(reason_code='policy_denied')
            return AccessDecision(True, 'synthetic_permission', principal.subject_reference, policy.revision)
        except Exception:
            # Never return session input, raw claims, or authority exceptions.
            return AccessDecision(reason_code='verification_failed')
