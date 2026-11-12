"""Synthetic, tokenless identity/session contracts. No network, keys or persistence.

Trusted installation is required. These fixtures are not authentication for real
people. Future provider implementations require separate review and are NOT
accepted automatically by SyntheticSessionAuthority.
"""
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Protocol
import re

from .json_io import strict_json_loads
from .synthetic_identity import ROLE_ACTIONS, PRIVILEGED


class IdentityDenied(PermissionError):
    def __init__(self):super().__init__('Synthetic identity/session denied')


def ref(value):
    if type(value) is not str or re.fullmatch(r'syn-[a-z0-9_-]{1,120}',value) is None:raise IdentityDenied()


def revision(value):
    if type(value) is not int or value<1:raise IdentityDenied()


def instant(value):
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset()!=timedelta(0):raise IdentityDenied()


def references(values):
    if type(values) is not tuple or len(values)>32:raise IdentityDenied()
    for value in values:ref(value)
    if len(values)!=len(set(values)):raise IdentityDenied()


@dataclass(frozen=True)
class IdentityEvidence:
    reference: str
    challenge_reference: str
    provider_reference: str
    issuer_reference: str
    audience_reference: str
    external_subject_reference: str
    tenant_reference: str
    authentication_context_reference: str
    assurance: str
    methods: tuple[str,...]
    authenticated_at: datetime
    issued_at: datetime
    expires_at: datetime
    dataset: str = 'synthetic'

    def validate(self):
        for name in ('reference','challenge_reference','provider_reference','issuer_reference','audience_reference','external_subject_reference','tenant_reference','authentication_context_reference'):ref(getattr(self,name))
        references(self.methods)
        if self.dataset!='synthetic' or self.assurance!='syn-mfa' or len(self.methods)<2 or not set(self.methods)<={'syn-factor-possession','syn-factor-knowledge','syn-factor-inherence'}:raise IdentityDenied()
        for value in (self.authenticated_at,self.issued_at,self.expires_at):instant(value)
        if not self.authenticated_at<=self.issued_at<self.expires_at or self.expires_at-self.authenticated_at>timedelta(minutes=5):raise IdentityDenied()


def decode_evidence(raw):
    try:
        if type(raw) is not bytes or len(raw)>16384:raise IdentityDenied()
        value=strict_json_loads(raw.decode('utf-8'))
        if type(value) is not dict or set(value)!=set(IdentityEvidence.__dataclass_fields__):raise IdentityDenied()
        if type(value['methods']) is not list:raise IdentityDenied()
        value['methods']=tuple(value['methods'])
        for field in ('authenticated_at','issued_at','expires_at'):value[field]=datetime.fromisoformat(value[field])
        evidence=IdentityEvidence(**value);evidence.validate();return evidence
    except Exception:raise IdentityDenied() from None


class IdentityProvider(Protocol):
    """Future trusted verifier seam, never a browser JSON authority.

    Implementations must verify raw protocol evidence OUTSIDE these contracts;
    raw credentials/tokens are never accepted or serialized by this layer.
    """
    def resolve(self,evidence_reference: str) -> IdentityEvidence | None: ...


class DeterministicIdentityProvider:
    """Explicit fixed synthetic evidence only; no tokens, keys, OAuth or network."""
    def __init__(self,evidence=()):
        self._evidence={}
        for index,item in enumerate(evidence):
            if index>=4096:raise IdentityDenied()
            if type(item) is not IdentityEvidence:raise IdentityDenied()
            item.validate()
            if item.reference in self._evidence:raise IdentityDenied()
            self._evidence[item.reference]=item
    def resolve(self,evidence_reference):
        ref(evidence_reference);return self._evidence.get(evidence_reference)


@dataclass(frozen=True)
class SubjectClaims:
    subject_reference: str
    external_subject_reference: str
    provider_reference: str
    tenant_reference: str
    revision: int
    roles: tuple[str,...]
    departments: tuple[str,...] = ()
    teams: tuple[str,...] = ()
    executives: tuple[str,...] = ()
    disabled: bool = False

    def validate(self):
        for value in (self.subject_reference,self.external_subject_reference,self.provider_reference,self.tenant_reference):ref(value)
        revision(self.revision)
        if type(self.disabled) is not bool or type(self.roles) is not tuple or not self.roles or any(type(role) is not str for role in self.roles) or len(self.roles)!=len(set(self.roles)) or not set(self.roles)<=ROLE_ACTIONS.keys() or len(set(self.roles)&PRIVILEGED)>1:raise IdentityDenied()
        for values in (self.departments,self.teams,self.executives):references(values)


@dataclass(frozen=True)
class ScopeRequirement:
    roles: tuple[str,...]
    department: str | None = None
    team: str | None = None
    executive: str | None = None
    sensitive: bool = False

    def validate(self):
        if type(self.roles) is not tuple or not self.roles or any(type(role) is not str for role in self.roles) or len(self.roles)!=len(set(self.roles)) or not set(self.roles)<=ROLE_ACTIONS.keys() or type(self.sensitive) is not bool:raise IdentityDenied()
        for v in (self.department,self.team,self.executive):
            if v is not None:ref(v)


@dataclass(frozen=True)
class SessionPolicy:
    provider_reference: str
    issuer_reference: str
    audience_reference: str
    absolute_seconds: int = 28800
    inactivity_seconds: int = 900
    reauthentication_seconds: int = 300

    def validate(self):
        for v in (self.provider_reference,self.issuer_reference,self.audience_reference):ref(v)
        for v in (self.absolute_seconds,self.inactivity_seconds,self.reauthentication_seconds):
            if type(v) is not int or not 1<=v<=28800:raise IdentityDenied()
        if self.inactivity_seconds>self.absolute_seconds or self.reauthentication_seconds>300:raise IdentityDenied()


@dataclass(frozen=True)
class SessionRecord:
    reference: str
    subject: SubjectClaims
    evidence: IdentityEvidence
    revision: int
    issued_at: datetime
    last_activity_at: datetime
    absolute_expires_at: datetime
    revoked: bool = False


@dataclass(frozen=True)
class IdentityDecision:
    sequence: int
    subject_reference: str | None
    tenant_reference: str | None
    operation: str
    allowed: bool
    code: str
    at: datetime

    def validate(self):
        revision(self.sequence);instant(self.at)
        if type(self.allowed) is not bool or self.operation not in ('issue','validate','authorize','reauthenticate','revoke','entitlements') or self.code!=('allowed' if self.allowed else 'denied'):raise IdentityDenied()
        if (self.subject_reference is None)!=(self.tenant_reference is None):raise IdentityDenied()
        for value in (self.subject_reference,self.tenant_reference):
            if value is not None:ref(value)


class DecisionJournal:
    """Bounded technical records only. No claims, evidence, session IDs or tokens."""
    def __init__(self,capacity=4096):
        if type(capacity) is not int or not 1<=capacity<=65536:raise IdentityDenied()
        self.capacity=capacity;self._rows=[]
    def append(self,decision):
        if type(decision) is not IdentityDecision or len(self._rows)>=self.capacity:raise IdentityDenied()
        decision.validate()
        if decision.sequence!=len(self._rows)+1:raise IdentityDenied()
        self._rows.append(decision)
    def snapshot(self):return tuple(self._rows)


class SyntheticSessionAuthority:
    """Process-local, synthetic contracts. State/replay updates follow audit append.

    No durable persistence is claimed: restart discards all sessions and receipts.
    One RLock linearizes operations and guarded gateway leases with revocation.
    """
    def __init__(self,provider,subjects,policy,clock,journal=None,capacity=256):
        if type(provider) is not DeterministicIdentityProvider or type(policy) is not SessionPolicy or not callable(clock) or type(capacity) is not int or not 1<=capacity<=1024:raise IdentityDenied()
        policy.validate();self.policy=policy;self.provider=provider;self.clock=clock
        self.journal=journal if journal is not None else DecisionJournal()
        if not isinstance(self.journal,DecisionJournal):raise IdentityDenied()
        self._subjects={};self._sessions={};self._used=set();self._requests=set();self._lock=RLock();self._last=None;self.capacity=capacity;self._sequence=0;self._guard_counter=0
        for index,subject in enumerate(subjects):
            if index>=capacity*4:raise IdentityDenied()
            if type(subject) is not SubjectClaims:raise IdentityDenied()
            subject.validate()
            if subject.subject_reference in self._subjects or any((s.provider_reference,s.external_subject_reference,s.tenant_reference)==(subject.provider_reference,subject.external_subject_reference,subject.tenant_reference) for s in self._subjects.values()):raise IdentityDenied()
            self._subjects[subject.subject_reference]=subject

    def _now(self):
        try:
            now=self.clock();instant(now)
            if self._last is not None and now<self._last:raise IdentityDenied()
        except Exception:raise IdentityDenied() from None
        self._last=now;return now
    def _decision(self,operation,allowed,now,subject=None):
        try:self.journal.append(IdentityDecision(self._sequence+1,subject.subject_reference if subject else None,subject.tenant_reference if subject else None,operation,allowed,'allowed' if allowed else 'denied',now))
        except Exception:raise IdentityDenied() from None
        self._sequence+=1
    def _evidence(self,reference,challenge,subject,now):
        ref(reference);ref(challenge)
        if len(self._used)>=self.capacity*64:raise IdentityDenied()
        item=self.provider.resolve(reference)
        if type(item) is not IdentityEvidence:raise IdentityDenied()
        item.validate()
        if ((item.provider_reference,item.issuer_reference,item.audience_reference)!=(self.policy.provider_reference,self.policy.issuer_reference,self.policy.audience_reference)
                or (item.provider_reference,item.external_subject_reference,item.tenant_reference)!=(subject.provider_reference,subject.external_subject_reference,subject.tenant_reference)
                or item.challenge_reference!=challenge or not item.issued_at<=now<item.expires_at or item.authenticated_at>now
                or (item.provider_reference,item.reference) in self._used or ('challenge',challenge) in self._used):raise IdentityDenied()
        return item
    def _live(self,reference,expected_revision,subject_reference,tenant,now):
        ref(reference);ref(subject_reference);ref(tenant);revision(expected_revision)
        record=self._sessions.get(reference)
        if record is None or record.revoked or record.revision!=expected_revision or (record.subject.subject_reference,record.subject.tenant_reference)!=(subject_reference,tenant):raise IdentityDenied()
        current=self._subjects.get(subject_reference)
        if current!=record.subject or current.disabled or not record.issued_at<=now<record.absolute_expires_at or now-record.last_activity_at>=timedelta(seconds=self.policy.inactivity_seconds):raise IdentityDenied()
        return record
    def _request(self,reference):
        ref(reference)
        if reference in self._requests or len(self._requests)>=self.capacity*64:raise IdentityDenied()
    def issue(self,reference,subject_reference,evidence_reference,challenge):
        with self._lock:
            now=self._now()
            try:
                ref(reference);ref(subject_reference)
                subject=self._subjects.get(subject_reference)
                if subject is None or subject.disabled or reference in self._sessions or len(self._sessions)>=self.capacity:raise IdentityDenied()
                evidence=self._evidence(evidence_reference,challenge,subject,now)
                result=SessionRecord(reference,subject,evidence,1,now,now,now+timedelta(seconds=self.policy.absolute_seconds))
                self._decision('issue',True,now,subject)
                self._sessions[reference]=result;self._used.update(((evidence.provider_reference,evidence.reference),('challenge',challenge)))
                return result
            except Exception:
                self._decision('issue',False,now);raise IdentityDenied() from None
    def check(self,reference,expected_revision,subject_reference,tenant,request_reference,scope=None):
        with self._lock:
            now=self._now()
            try:
                self._request(request_reference)
                record=self._live(reference,expected_revision,subject_reference,tenant,now)
                if scope is not None:
                    if type(scope) is not ScopeRequirement:raise IdentityDenied()
                    scope.validate();s=record.subject
                    if not set(scope.roles)<=set(s.roles) or any(v is not None and v not in values for v,values in ((scope.department,s.departments),(scope.team,s.teams),(scope.executive,s.executives))):raise IdentityDenied()
                    if scope.sensitive and now-record.evidence.authenticated_at>=timedelta(seconds=self.policy.reauthentication_seconds):raise IdentityDenied()
                self._decision('authorize' if scope is not None else 'validate',True,now,record.subject)
                self._sessions[reference]=replace(record,last_activity_at=now);self._requests.add(request_reference)
                return self._sessions[reference]
            except Exception:
                self._decision('validate',False,now);raise IdentityDenied() from None
    def reauthenticate(self,reference,expected_revision,subject_reference,tenant,evidence_reference,challenge):
        with self._lock:
            now=self._now()
            try:
                record=self._live(reference,expected_revision,subject_reference,tenant,now)
                evidence=self._evidence(evidence_reference,challenge,record.subject,now)
                if evidence.authenticated_at<=record.evidence.authenticated_at:raise IdentityDenied()
                result=replace(record,evidence=evidence,revision=record.revision+1,last_activity_at=now)
                self._decision('reauthenticate',True,now,record.subject)
                self._sessions[reference]=result;self._used.update(((evidence.provider_reference,evidence.reference),('challenge',challenge)));return result
            except Exception:
                self._decision('reauthenticate',False,now);raise IdentityDenied() from None
    def revoke(self,reference,expected_revision):
        with self._lock:
            now=self._now()
            try:
                ref(reference);revision(expected_revision);record=self._sessions.get(reference)
                if record is None or record.revoked or record.revision!=expected_revision:raise IdentityDenied()
                self._decision('revoke',True,now,record.subject)
                result=replace(record,revoked=True,revision=record.revision+1);self._sessions[reference]=result;return result
            except Exception:
                self._decision('revoke',False,now);raise IdentityDenied() from None
    def revise_subject(self,subject,expected_revision):
        with self._lock:
            now=self._now()
            try:
                revision(expected_revision)
                if type(subject) is not SubjectClaims:raise IdentityDenied()
                subject.validate();prior=self._subjects.get(subject.subject_reference)
                if prior is None or prior.revision!=expected_revision or subject.revision!=expected_revision+1 or subject.tenant_reference!=prior.tenant_reference or (subject.provider_reference,subject.external_subject_reference)!=(prior.provider_reference,prior.external_subject_reference):raise IdentityDenied()
                self._decision('entitlements',True,now,subject);self._subjects[subject.subject_reference]=subject
            except Exception:
                self._decision('entitlements',False,now);raise IdentityDenied() from None
    def snapshot(self):
        with self._lock:return tuple(self._sessions.values())
    def close(self):
        with self._lock:
            self._sessions.clear();self._used.clear();self._requests.clear();self._subjects.clear()


@dataclass(frozen=True)
class SessionBinding:
    session_reference: str
    subject_reference: str
    tenant_reference: str
    session_revision: int
    policy_revision: int


class ContractGuard:
    """Optional trusted installation, never payload-selected; additional denial only."""
    def __init__(self,authority,bindings,requirements):
        if type(authority) is not SyntheticSessionAuthority:raise IdentityDenied()
        self.authority=authority;self.bindings=dict(bindings);self.requirements=dict(requirements)
        for legacy,b in self.bindings.items():
            ref(legacy)
            if type(b) is not SessionBinding:raise IdentityDenied()
            for v in (b.session_reference,b.subject_reference,b.tenant_reference):ref(v)
            revision(b.session_revision);revision(b.policy_revision)
        for (action,resource),scope in self.requirements.items():
            ref(resource)
            if not any(action in actions for actions in ROLE_ACTIONS.values()) or type(scope) is not ScopeRequirement:raise IdentityDenied()
            scope.validate()
    def validate(self,legacy,tenant,policy_revision,principal=None,action=None,resource=None):
        with self.authority._lock:
            try:
                ref(legacy);ref(tenant);revision(policy_revision)
                b=self.bindings.get(legacy)
                if b is None or (tenant,policy_revision)!=(b.tenant_reference,b.policy_revision):raise IdentityDenied()
                scope=None
                if action is not None:
                    scope=self.requirements.get((action,resource))
                    if scope is None:raise IdentityDenied()
                subject=self.authority._subjects.get(b.subject_reference)
                if subject is None or (principal is not None and (principal.subject_reference!=subject.subject_reference or principal.tenant_reference!=tenant or set(principal.roles)!=set(subject.roles))):raise IdentityDenied()
            except Exception:
                self.authority._decision('validate',False,self.authority._now())
                raise IdentityDenied() from None
            self.authority._guard_counter+=1
            return self.authority.check(b.session_reference,b.session_revision,b.subject_reference,tenant,'syn-contract-check-'+str(self.authority._guard_counter),scope)
    @contextmanager
    def lease(self,legacy,tenant,policy_revision):
        with self.authority._lock:
            self.validate(legacy,tenant,policy_revision)
            yield
