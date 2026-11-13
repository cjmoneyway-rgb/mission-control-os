# Phase 2E M3 — Mocked HubSpot projection contracts

## Scope, provenance and authority

Baseline: `79ab81bdb7edb37ca106b36bfb4bbd148cf348b9`, merged PR #17 including M1
and M2. Branch: `phase-2e/hubspot-mocked-projection-contracts`.
This is a fixed fictional contact/company projection, not HubSpot, a second CRM,
an operational ledger or a production adapter. No deal or relationship-lifecycle
fields are admitted. Existing [assessment](phase-2e-production-integration-readiness.md),
[roadmap](phase-2e-roadmap.md), [connector gates](phase-2e-connector-gates.md),
[decisions](phase-2e-ceo-decisions.md), [acceptance/rollback plan](phase-2e-acceptance-plan.md),
[M1 contracts](phase-2e-identity-session-contracts.md) and
[M2 recovery design](phase-2e-storage-recovery-audit-design.md) remain authoritative.

| Component | Actual capability / exclusion |
| --- | --- |
| `hubspot_projection.py` | Immutable contract records and an explicitly installed, bounded process-local fictional cache; zero I/O, transport, database access or domain mutation |
| `syn-hubspot` descriptor | Unchanged, `enabled=False`, `state=unresolved`; transmit still unconditionally denied |
| Future production integration | Not implemented. Needs verified vendor semantics, identity/custody/admission/reliability/operations, C0–C6 and separate authorization; a mock pass cannot supply them |

Mission Control remains operational authority for routing, approvals, policy,
execution intentions, revisions, receipts and measurement. PostgreSQL remains
protected authoritative persistence for its approved operational records. HubSpot
owns approved relationship/commercial facts; an observation never approves MC
work. Slack remains communication; the proposed 2nd Brain remains institutional
knowledge. Neither is implemented or connected. Seven connectors remain disabled.

## Trusted installation and data ownership

Only trusted Python installation may supply `Mapping` and fixed `Observation`
records. Runtime calls accept installed fixture references, not observations,
provider responses, URLs or browser-selected authority. Unknown fixture references
deny. Installers must author non-identifying fictional fixtures from scratch;
`synthetic` declarations and `syn-` prefixes do not prove data is safe. Trusted
Python/OS access is a prerequisite, not an adversarial-code sandbox.

Each mapping fixes tenant, fictional portal, contact/company type, source object,
purpose, classification and visibility references; independent exact read grants
control access to the mapping. All statuses, associations and merge targets must
be explicitly allowlisted at installation. The module does not decide or duplicate
domain visibility/routing policy. A mapping-level grant covers its installed,
minimized view, not all commercial records or another tenant.

References in fictional source fields must match the bounded opaque
`syn-fictional-` vocabulary. Real names, email, telephone/address, financial terms,
notes, attachments, arbitrary properties, URLs, credentials/tokens, raw provider
bodies, approval proof, roles, permissions, instructions, deal and relationship-
lifecycle fields are excluded. Unknown properties reject, including apparently
harmless synthetic additions. Source contacts cannot identify authenticated users.
Opaque association references are observations only, never automatic MC journey
reparenting; one contact is not restricted to one journey.

## Contract and bounds

| Record | Fields and constraints |
| --- | --- |
| `Observation` | Unique installed observation reference; mapping/portal/object identity; object type contact/company; positive source version; source-update ≤ observation ≤ verification times; active/merged/archived/deleted/unknown/unavailable state; allowlisted status/association tuples; merge/tombstone references; schema 1, dataset synthetic; derived canonical SHA-256 digest |
| `Mapping` | Server-owned binding/purpose/classification/visibility, approved status/association/merge-target tuples and explicit freshness seconds |
| `Projection` | Minimized source binding, installed purpose/classification/visibility, projection revision, explicit state, source version/times, active-only status/association references, merge/tombstone and observation digest; immutable, synthetic/schema 1 |
| `Decision` | Sequence, request/correlation/mapping reference when allowed, source/projection versions, allowed decision, fixed reason code, timestamp, schema 1. Denials omit rejected references |

Installation decoder accepts at most 16 KiB strict UTF-8 JSON with exactly all
Observation fields. Duplicate keys, nonfinite numbers, missing/unknown fields,
invalid Unicode, invalid types/booleans as revisions, nested values and oversized
collections fail with one sanitized error. Source references are at most 100
characters; collections contain at most 16 distinct opaque references. At most 16
mappings, 128 fixtures and 512 accepted replay identifiers are retained. Exhaustion
denies rather than evicting dedup evidence. Journal defaults to 2048 records,
configurable 1–8192. These are synthetic technical bounds, not production policy.

UTC times must be aware with zero offset. Freshness uses original source-update
time, never a retry's arrival time. Mapping freshness is explicitly installed,
1–3600 seconds (demo 300). Backward injected clock movement denies; timestamps
cannot prove authenticity. Source-version ordering is an invented fixture contract,
not verified HubSpot API behavior. The demo uses wall-clock UTC only to satisfy
existing legacy identity validity; for any supplied start instant its fixtures and
transitions are deterministic. It does not prove distributed clock robustness.

## Authorization, cache transitions and replay

Installation requires the exact existing `SyntheticAuthority` with an M1
`ContractGuard`. `operate` obtains the existing guard lease and invokes existing
`registry.read` authorization for the exact mapping. No role/action vocabulary is
added. Browser/source roles cannot grant access. Missing/expired/revoked sessions,
stale subject/binding/policy revisions, cross-tenant/portal access, absent grants,
deny grants and insufficient scopes fail closed. Existing MFA and duty checks
remain intact. This read grant authorizes technical fixture projection only,
not domain ingestion, approval or execution.

The module serializes its process-local operations with a lock; the M1 lease
preserves existing revocation ordering. Already-admitted work can finish before a
waiting revoker returns. No instantaneous cancellation or distributed lease claim.

Runtime calls distinguish session/policy revision, request and correlation
references, installed observation/source version and expected projection revision.
There is no MC domain revision or receipt mutation. Unknown or absent observations
produce an explicit `unknown` projection; unavailable remains `unavailable`. A stale
active observation yields `stale` with no commercial status/association fields.
None of these states means a successful empty relationship.

Explicit fixture replay requires expected projection revision. Request identifiers cannot be reused across bindings. Dedup signatures bind
tenant/portal/object type/object identity, fixture reference/version via canonical
digest, original expected revision and correlation reference. Exact
retries return the same immutable result only while it is still the current,
authorized, unexpired observation. After updates, revocation or expiry, old retries
deny rather than disclose obsolete state. A new request for the exact current
observation deduplicates without advancing projection revision and must carry the
current expected revision. Changed content under a used request conflicts.
Installation forbids duplicate observation identifiers, even with different bodies.
Lower/equal conflicting source versions and backward source-update time deny.
Higher source versions with unchanged semantic content also deny: changing only
times/version cannot refresh freshness. Association/status changes may produce a
new revision; no existing MC record changes.

Merged/archived/deleted observations require tombstones and expose no active
attributes. Merge targets are installed references, not traversal or automatic
mapping changes. Terminal states cannot resurrect within an installation.
`revoke_source` validates the same session, grant, source binding and required audit
before withdrawing all subsequent read/replay access; it provides no restore or
grant operation. Source withdrawal is a trusted local fixture operation, not a
vendor consent API, business approval or remotely exposed mutation.

All candidate values/results are validated and constructed before required audit
append and publication to cache/dedup state. On ordinary validation, authorization,
capacity or audit failure, no partial projection/request/revocation update occurs.
Existing M1 decision/replay/activity state and observed clock watermarks may advance
when identity checks ran; this module does not roll back independent security
decisions. It is not resilient to malicious injected Python, catastrophic memory
failure or a durable transaction substitute.

## Audit, privacy, deletion and recovery limitations

Audit stores only bounded immutable technical decisions. Denied rows omit raw
request/mapping/session values. No observation bodies, attributes, rejected values,
session material, token or approval proof enter the journal. Sink failure denies
publication, with sanitized errors and no raw fallback logs. The journal is
process-local demonstration evidence, not independent durable custody. Admission,
projection acceptance, domain commit and external receipt are distinct concepts;
no external receipt or delivery success is manufactured.

No retry loop, worker or reconciliation request exists. Unknown hypothetical
external outcomes remain unresolved; future transport must quarantine uncertainty
and reconcile under separate authorization, never blindly resend or promise
exactly-once behavior. M2 independent recovery and human restart gates still apply.

`close()` clears fixture mappings, observations, cache, replay identifiers and
withdrawals, then permanently denies use. It does not delete MC data or journal
history. Trusted installer owns M1 teardown; the demo closes both. A fresh process
cannot recover old dedup/tombstone/withdrawal history: no durable replay,
cross-process recovery, legal erasure, retention guarantee or production restart
safety is claimed. A new trusted installation is a new fictional test universe.
Journal can remain as minimized test evidence; it is not raw-source retention.

Real consent/lawful basis, class-specific retention/hold/deletion, source ACL
revocation windows, vendor copies and admission are unresolved D06 requirements.
IDs themselves can be confidential. No real record, even public contact data,
may be installed. Production identity, storage, audit custody, durable delivery,
HubSpot product/API permissions and semantics remain unverified.

## Demonstration and acceptance

```sh
python -B scripts/demo_hubspot_projection.py --synthetic-development
```

Explicit startup flag required. Demo shows authorized projection, exact duplicate,
stale-version/conflicting retry denial, cross-tenant denial, tombstone, merge,
seven disabled connectors and cleanup. It starts no listener/DB/container and
reads no credential or vendor account. Imports never start anything.

| Criteria | M3 proof scope / production exclusion |
| --- | --- |
| AT-01–03 | Reuse M1 sessions/scopes/exact grants; revoked/expired/substituted/denied identities fail. No real authentication or MFA proof |
| AT-07 | Minimized journal and audit-failure denial; no independent durable custody |
| AT-08 | Strict minimized field allowlist and synthetic-only installation; no real-data admission/consent proof |
| AT-10–11 | Seven disabled descriptors, no network/transport; mapping, merge, tombstone and authority separation; no vendor/webhook validation |
| AT-12 | Process-local duplicate/conflict/rollback/uncertainty cases; no durable outbox, external receipts or reconciliation |
| AT-15 | Source withdrawal/tombstone denies old views; no vendor erasure or durable deletion guarantee |
| AT-16 | Exact baseline/diff/hashes, preserved tests, actual result counts and cleanup; no operational authorization |

D01/D03 owners/SoD/custody, D06 admission/retention, D07 commercial owner/property
map/product/API semantics and D09 capacity remain unresolved. D02 identity,
D04/D05 storage/operations and D08 delivery automation also remain blocked.
All C0–C6 gates remain unfulfilled for production. M3 is the roadmap's conditional
contract/fixture slice after merged M1/M2, not a live integration or launch.
Full verification evidence and actual counts are recorded outside the repository
in `/workspace/phase-2e-m3-review/`. No historical count is forced.
