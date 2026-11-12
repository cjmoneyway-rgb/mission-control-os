# Phase 2E — Identity/session contract specification

[Synthetic architecture/threat model](phase-2e-identity-architecture.md) ·
[Authoritative assessment](phase-2e-production-integration-readiness.md).

**No production provider, token verification or human authentication is implemented.**
All records here are trusted synthetic fixtures or derived process-local state.
No OAuth client, password, raw access/refresh token, MFA secret or signing key is
accepted/generated/stored by the layer. No HTTP/OpenAPI route changes.

## Contracts and provenance

| Contract | Fields / invariant |
| --- | --- |
| `IdentityEvidence` | `reference`, `challenge_reference`, `provider_reference`, `issuer_reference`, `audience_reference`, `external_subject_reference`, `tenant_reference`, `authentication_context_reference`; `assurance`, `methods`; `authenticated_at`, `issued_at`, `expires_at`; `dataset=synthetic` |
| `IdentityProvider` | Future trusted `resolve(evidence_reference) -> IdentityEvidence or None` interface sketch; an unverified JSON object is not a verified identity. Actual production verification/DTO/versioning is separate future work, not a pluggable live adapter here |
| `DeterministicIdentityProvider` | Copies explicitly installed fixed evidence by unique reference; no network, secrets, key generation or tokens; at most 4096 fixtures. Only this exact provider type is accepted by `SyntheticSessionAuthority` |
| `SubjectClaims` | Stable internal `subject_reference`; mapped external subject/provider/tenant; entitlement `revision`; `roles`, `departments`, `teams`, `executives`; `disabled`. No email or display-name identity; duplicate internal/external tenant mappings deny |
| `SessionPolicy` | Exact trusted provider/issuer/audience references; absolute, inactivity and sensitive-reauthentication seconds. Explicit installed policy, never browser-selected |
| `SessionRecord` | Unique public synthetic session reference, immutable subject/evidence snapshot, security revision, issuance/last-activity/original absolute-expiry instants, revoked flag; derived only through authority operations |
| `ScopeRequirement` | Required role tuple plus optional department/team/executive reference and sensitive flag; all specified requirements must hold. Identity liveness alone is not business authorization |
| `SessionBinding` | Server-installed legacy-to-contract session reference, stable subject, tenant, contract session revision and existing policy revision; no token or approval evidence |
| `ContractGuard` | Exact legacy bindings and `(existing action, resource)` requirements. Unbound sessions/unlisted actions deny; it adds checks after existing authority checks, never grants a missing permission |
| `IdentityDecision` | Sequence, optional internal subject/tenant references, operation, allowed boolean, fixed allowed/denied code, UTC time. No session ID, raw claims/evidence, challenge, auth context, methods, token, exception text or confidential payload |
| `DecisionJournal` | Bounded process-local decision sequence; schema validates each row; append failure/exhaustion denies before state update. No file/database/archive writer or operational audit-custody claim |

References are restricted ASCII `syn-` opaque labels (at most 120 suffix characters),
not real addresses, URLs, credentials or proof. Prefixes never anonymize real data;
only genuinely synthetic fixtures may be installed. Scope tuples are unique and
bounded; role vocabulary reuses existing definitions and privileged-duty limits.
No new role/policy/approval vocabulary is created.

`decode_evidence(bytes)` accepts at most 16 KiB of strict UTF-8 JSON with exactly
all `IdentityEvidence` fields, including `dataset`. Unknown or missing fields,
duplicate keys, nonfinite numbers, invalid UTF-8, invalid references/types or token/
role additions reject with one constant `IdentityDenied` message. `methods` is a
JSON list converted to an immutable tuple; timestamps are aware UTC ISO-8601.
All other authority inputs are typed trusted installation objects, not new wire
APIs. Dataclass schema/decoder tests, not a changed OpenAPI contract, cover them.

Valid evidence has assurance `syn-mfa` and at least two distinct members of
`syn-factor-possession`, `syn-factor-knowledge`, `syn-factor-inherence`.
Authentication ≤ issuance < evidence expiry; evidence validity spans at most five
minutes. These are test metadata constraints, not cryptographic/MFA verification.
An issuer/audience/provider mismatch cannot be corrected by caller role claims.

## Policy bounds and decisions still required

Synthetic policy defaults mirror the assessment's candidate values: absolute
28,800 seconds, inactivity 900 seconds, sensitive reauthentication 300 seconds.
They are not approved production settings. Each configured duration is a positive
integer ≤28,800, inactivity cannot exceed absolute, and sensitive freshness cannot
exceed 300. Shorter test policies are supported; booleans are not integers here.
The legacy principal/MFA/service/policy rules continue to impose their own, possibly
shorter, limits. Production values/provider/service identity decisions remain D02/D03.

The injected clock returns aware UTC. Backward movement fails closed. This is a
synthetic clock contract, not resilient distributed time synchronization. Receipt
expiry is checked when issuing/reauthenticating; an already-derived session uses
its own absolute/idle bounds and sensitive freshness. It does not reuse an expired
receipt for a new session. Reauthentication requires a strictly later authentication
instant and a fresh exact same-subject/provider/tenant receipt/challenge.

## Operations and state transitions

| Operation | Required conditions | Success / failure effect |
| --- | --- | --- |
| `issue` | Known enabled subject, unique session ID, valid current exact provider/issuer/audience/subject/tenant receipt and challenge, unused evidence/challenge, capacity and journal available | Audit allowed decision, then create revision 1, fixed absolute deadline and consume receipt/challenge. Failure audits denial without creating or consuming identity state |
| `check` | Live exact session/security revision/subject/tenant, unchanged current entitlement snapshot, current absolute and idle windows, unique operation reference; validate every provided scope and fresh authentication for sensitive scope | Audit decision then advance activity and consume operation ID. Normal activity does not advance security revision or extend absolute lifetime. Failure leaves activity/state unchanged; replay denies |
| `reauthenticate` | Existing live exact session/revision/binding, fresh unused matching evidence/challenge with later authentication | Audit, replace auth metadata, increment revision, refresh activity; preserve original absolute deadline. Old guard binding/revision denies until explicitly rebound by trusted code |
| `revoke` | Known unrevoked session and exact current revision | Audit then set revoked and increment revision; retain tombstone. Unknown/stale/duplicate revoke denies; no expiry/revocation fallback |
| `revise_subject` | Trusted administrative installation, exact prior entitlement revision and next revision; stable internal/provider/external/tenant binding | Audit then replace entitlements; old sessions fail snapshot equality even if their session revision is unchanged. Disabled subjects cannot issue. No public administration route is exposed |
| `close` | Trusted teardown | Discard subjects/sessions/replay state; old references cannot validate. Minimized journal may remain as test evidence; it contains no credentials or session/evidence references |

Capacity defaults: 256 total session/tombstone records (configurable 1–1024), at
most four times that many subject fixtures; replay stores bounded by 64 times
session capacity; default journal 4096 records (configurable at most 65,536).
Exhaustion denies; no automatic tombstone/replay eviction or hidden session renewal.
The audit and clock watermarks are security metadata, not business commit records.
All manager transitions and gateway leases use one reentrant lock. Guard-generated
operation references are sequenced across all guards sharing that authority.

## Compatibility and revision boundaries

Existing `SyntheticAuthority.resolve` first performs its existing session, MFA,
duty and policy checks, then the opt-in binding check. `authorize` first enforces
its original exact grants/deny precedence, then the supplemental scope requirement.
The gateway lease preserves the original handler body. All request freshness,
expected domain revision, idempotency, tenant identity, approvals, audit, route,
security headers, CORS/CSRF and browser confirmation controls remain mandatory.
New claims cannot supply approval, change tenant, skip original policy or create
operational authorization. `ScopeRequirement` never reimplements routing,
responsible executive ownership, registry or lifecycle logic.

A request admitted before revocation may finish before the waiting revoker's
linearization point. After revocation returns, no later guarded request succeeds.
Already committed domain work is not undone. Direct trusted storage calls outside
a gateway lease use their existing transaction/commit rechecks; a whole-operation
lease must be explicitly used if that stronger ordering is required. This contract
does not claim distributed/instantaneous revocation or arbitrary-thread preemption.

## Evidence, persistence and production exclusions

Sessions, provider assertions and replay state are intentionally **not persisted**.
No new table, migration or archive format exists. PostgreSQL tests use the existing
services and real disposable 17.11 transactions: successful idempotent proposal,
revocation/expiry denial, exact existing policy, actual uncommitted-write rollback,
and full archive validation with no new identity/authentication data. An independent
existing synthetic audit identity witnesses the same store; it is not an identity
exporter or a second database. Raw marker fields are rejected before persistence.

No raw credential/token exists in the new layer's schema, demo output or journal.
Negative cases use public nonsecret markers, not actual credentials. Existing
synthetic HMAC test fixtures are unchanged; the new layer creates no cryptographic
keys. Production IdP signature/MFA verification, enrollment/recovery/offboarding,
durable multiworker session/revocation/nonce storage, encrypted custody, independent
security auditing, real data admission and organizational authority are unresolved
future decisions. No Auth0/Okta/Entra/Google/GitHub/other provider is selected or
connected. HubSpot, Slack and 2nd Brain work is out of scope. Seven connectors remain
disabled and all changes require new CEO review before commit or push.
