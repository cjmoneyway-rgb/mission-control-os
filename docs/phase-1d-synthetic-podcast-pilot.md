# Phase 1D: inactive synthetic podcast-guest lifecycle

Uncommitted technical proposal based on verified main `e357a7a63a884e85a979f267f3eaf877ea51589f`,
branch `phase-1d/synthetic-podcast-guest-pilot`. It extends the existing Mission
Control package, identity/policy boundary, PostgreSQL schema, registry, rules,
work packets, audit metadata, and executive visibility model. It creates no second
application and has no operational-engine or provider wiring.

## Scope and sequence

The [routing and lifecycle matrix](phase-1d-routing-lifecycle-matrix.md) defines all
16 connected synthetic stages. One immutable intake enters once with classification
`syn-entry-class`; every later classification is linked history. A GuestJourney
contains only tenant, journey, guest and intake references, the permanent entry
classification, revision 1, schema revision 1, state `inactive`, and exact digest.
No guest name, email, meeting details, transcript, contact, personnel assignment,
confidential registry or complete Phase One material is accepted by these fixtures.

GuestEvent proposals contain tenant/journey/event references, exact proposal revision,
opaque stage and deterministic classification, predecessor and dependencies, evidence,
outcome and handoff references, exact rule revision/digest, exact approval reference,
and optional final completion/closure token. Unknown fields, duplicate JSON keys,
malformed references, self-dependencies, classification mismatches and non-inactive
states fail validation. The stages use restricted opaque tokens; this does not make
real information safe merely because it is prefixed `syn-`.

1. A separately authenticated policy administrator registers synthetic references.
   A writer persists the two generic departments and the 16 deterministic rule
   revisions. A separate issuer approves each exact department and rule revision.
2. An authorized writer calls `start_journey` with one immutable intake and journey.
   A unique tenant/intake key and transactional receipt prevent duplicate entry.
3. A writer appends an event proposal against an expected proposal head. The proposal
   is immutable; a revision creates another row and CAS head, invalidating old proof.
   The responsible synthetic issuer approves that exact persisted proposal digest,
   tenant, journey, event, revision, policy and validity interval. Self-approval fails.
4. `advance_event` independently verifies current policy, latest approved rule and
   department revisions, exact event approval and synthetic evidence facts. Mission
   Control deterministically classifies the opaque stage; there is no model call.
5. The next stage and predecessor must match the last accepted stage. An unaccepted
   additional dependency records an explicit blocked attempt, with no packets or
   deliverables. Its transaction version advances but its completed stage does not.
   An identical retry returns the same blocked result. A new reviewed attempt is
   required for recovery; blocked history and its receipt are never rewritten.
6. A valid event atomically appends its decision, inactive packet(s), source/event
   links, outcome/handoff links, journal events and idempotency receipt, then advances
   a compare-and-swap head. Original classification and the entire original journey
   remain intact. The complete happy path has 16 events and 19 packets.
7. The final event explicitly records synthetic completion or closure. This is
   progress metadata only. All records, rules, packets and deliveries stay inactive.

Rules/department/event evidence and the exact persisted policy digest are rechecked
on clean transaction exit. Missing,
expired, revoked, mismatched or unverifiable proof blocks both new work and exact
retries. Existing policy deny precedence, current persisted-policy binding, MFA,
individual identities, short-lived service claims and privileged-duty separation
remain in force. No system is connected and no operational guest pilot is launched.

## Existing contracts and visibility

Packets reuse the Phase 1C DepartmentPacket and exact `routing_links` constraints.
The packet's source-event reference continues to identify the single intake. New
`pilot_packet_links` supplies the additional lifecycle-event-to-packet relationship,
so multiple events do not masquerade as new intakes. Packet IDs bind tenant, intake,
lifecycle event and department. Exact registry/rule revision and digest, responsible
executive, current and original classification, dependencies, action, outcomes,
handoffs and idempotency reference remain connected.

The existing minimized executive/team/command/control/governance projections are
reused. Command represents CEO Command Center; control represents Mission Control.
Full-journey reading requires a separate exact journey permission. Projection
visibility grants neither assignment, approval, activation nor external processing.
Only an individually bound executive can record team visibility for their department;
this is still an inactive decision and does not create a live task or notification.

An optional `SyntheticGrant.subject_reference` narrows a role grant to one verified
subject. `None` preserves existing role-only semantics; scoped grants match only
that subject, and applicable explicit denies still override allows. New fixtures
use separate alpha/beta identities and subject-scoped executive/team grants to
prove that shared reader roles do not leak department or team visibility. Oversight
uses independently scoped audience grants. No real identity configuration is added.

Adding the optional field changes newly serialized synthetic policy digests. Existing
persisted policy documents are not rewritten or silently upgraded. Reconfiguration
or restore requires an exact separately trusted policy snapshot; older configurations
that do not match must remain denied until a new revision is explicitly reviewed.
The Phase 1A engine, CLI, provider gate, audit implementation, all older migrations
and v1 archive guard remain unchanged.

## PostgreSQL transaction and schema extension

The forward-only `0003_synthetic_podcast_pilot.sql` extends the same `mc_syn` schema.
It has no seeds or down migration. Explicit authorized migration uses the existing
advisory lock and migration ledger, verifies the Phase 1A–1C baseline checksums, and
records its own checksum. No migration runs on import or ordinary application startup.
Only the disposable PostgreSQL 17.11 environment runs the proof.

| New table | Persisted responsibility |
|---|---|
| pilot_journeys | Immutable root, unique source intake, permanent classification |
| pilot_proposals | Append-only event revisions and author/policy metadata |
| pilot_proposal_heads | Exact revision CAS heads |
| pilot_evidence | Exact event/tenant/journey/revision/digest approval, issuer and signed validity interval |
| pilot_revocations | Append-only revocations |
| pilot_events | Ordered hash-linked accepted/blocked event history |
| pilot_heads | CAS transaction version, last accepted event, completed-stage count and progress; inactive state |
| pilot_decisions | Deterministic classification, exact rule/event evidence, explicit blocked/accepted result |
| pilot_packet_links | Lifecycle event to exact existing Department Work Packet revision |
| pilot_deliverables | Event/packet-linked opaque handoff and outcome references |

Every table uses tenant-scoped composite keys/references, `dataset='synthetic'`,
forced RLS, and no runtime DELETE/TRUNCATE/DDL privileges. UPDATE is restricted to
CAS heads; histories have immutable-update/delete triggers. Database constraints
require inactive state, valid predecessor chains, exact event/rule links, valid
stage ordering, accepted-versus-blocked packet behavior, complete outcome/handoff
links, final heads consistent with preserved history, and a complete linked decision. Existing deferred packet/intake/rule checks remain in place. All public
operations use the existing guarded SERIALIZABLE transaction: caught errors doom
partial work; omission of explicit commit or an exception after requesting commit
rolls back. Concurrent writers conflict instead of duplicating stage packet sets.

## Complete synthetic export, restore and integrity

The reviewed `0003_archive_manifest.json` describes columns/types/nullability,
primary/unique keys and foreign keys for all **34** existing and new tables. It was
constructed from disposable PostgreSQL 17.11 after applying the three reviewed
forward-only SQL migrations; no real records appear in the manifest.

`pilot_archive.py` introduces a separate complete archive format. The old v1 format
continues to refuse extended schemas, preserving the Phase 1C fail-closed boundary.
Complete export requires the exact backup-export permission, checks the installed
schema against the manifest (including forced RLS), and verifies installed migration
checksums. One SERIALIZABLE snapshot captures every tenant row across all tables,
including policy, original Phase 1B records, registry/rules/evidence, proposals,
blocked attempts, revisions, history, packets, deliverables, receipts and audit.

A narrowly scoped read-only SQL SECURITY DEFINER function exposes only shared
migration IDs/checksums/application timestamps. It has a fixed `pg_catalog` search
path, no parameters, qualified table reference, revoked PUBLIC execution and only
the synthetic runtime grant. It cannot write data, read directives or bypass tenant
record access. Shared schema-ledger metadata is provenance, not tenant data.

The archive binds exact format, dataset, tenant, manifest digest, migration provenance,
per-table row counts and digests, complete table inventory, overall checksum and ephemeral synthetic
custody proof. Verification checks schema/type/key/FK completeness, nested contracts,
revision/head continuity, permanent name claims, approvals/signatures, source links,
deterministic routing results, hash chains, blocked/accepted progression, receipts,
and exact packet/outcome/handoff completeness. Historical expired/revoked proofs are
preserved and verified as historical signatures, not authorized for current reuse.

The correction to the initial Phase 1D implementation reconciles journal entries
against the retained journeys, lifecycle decisions, packets, revisions, receipts and
inactive team visibility. Empty journals and internally consistent prefixes are
rejected when those records require omitted entries. Each required operation batch
must occur exactly once and contiguously, with lifecycle and packet revision order
preserved. Unknown/orphan journal operations and duplicate operation receipts fail
closed. Foreign keys and nested references cover approval, rule, department,
visibility, handoff, outcome and idempotency relationships. Archive table-array order
is immaterial; journal sequences, linked predecessors and recipient order are not.

All 34 table names must occur in the data, signed count inventory and digest inventory,
including empty tables. Counts, keys, revisions, references and content must agree.
Complete format `syn-pilot-export-v2` requires signed counts. Pre-correction
complete v1 archives are rejected; re-export from
the synthetic source rather than silently upgrading an old archive. This does not
alter the older baseline-format rejection for extended databases.

These checks establish completeness relative to the retained, signed graph. They
cannot detect coordinated removal of an entire independent history by an actor
with signing custody, or establish records that were never captured. Independent
historical checkpoints remain a separate production requirement. A successful
round-trip preserves every captured tenant row; the only added row is a minimized
restore audit decision. Migration application timestamps belong to the destination
ledger. An uncertain connection outcome after a server has actually committed
requires reconciliation; rollback is not a claim to undo an already committed
transaction.

Restore requires separate migration/restore authority and a completely empty tenant
in a separately initialized disposable database with matching schema/migration hashes.
Unknown schema drift, changed content, incomplete tables or links, cross-tenant data,
wrong or untrusted signing custody, nonempty targets and invalid graphs are rejected.
Untrusted custody objects are rejected before any signing callback is invoked. The archive is detached from caller-owned mutable data before validation. Dependency-
ordered insertion, a fresh database read of all 34 tables, exact source-row comparison,
semantic reconciliation and forced deferred SQL checks occur in one SERIALIZABLE
transaction. No row is inserted until preflight passes. Preflight, insertion,
reconciliation, integrity and database commit failures abort the transaction; a
caught operation error also prevents commit. Nonempty tenants are never merged or
overwritten, and other tenants and the shared migration ledger remain unchanged. All source audit
records survive; restore adds one minimized audit decision. The destination's own
shared migration timestamps remain authoritative and are not overwritten; source
migration timestamps stay in the signed archive provenance. Restoration does not
activate anything or grant new policy permissions.

File publication uses a private temporary file, fsync and atomic no-replace link.
Archives are mode 0600, plaintext and synthetic only; existing files cannot be
overwritten. A failed or interrupted restore rolls back all inserted tenant rows.
No archive imports, rewrites, quarantines anew or modifies existing legacy logs.

## Validation and manual workflow

The workflow retains `workflow_dispatch` only, standard Ubuntu 24.04, `contents: read`,
no repository/organization/environment secrets, no artifacts/caches or deployments,
job-generated synthetic credentials and disposable PostgreSQL 17.11 pinned by the
existing immutable image digest. Bootstrap host trust is loopback-only and is replaced
with SCRAM before tests; bootstrap login is disabled, and runtime/admin credentials
are distinct. Credentials are removed and GitHub destroys the service on job end.

Existing native Node.js 24 official pins are unchanged:

- checkout v6.0.1: `8e8c483db84b4bee98b60c0593521ed34d9990e8`
- setup-python v6.1.0: `83679a892e2d95755f2dac6acb0bfd1e9ac5d548`
- PostgreSQL image: `postgres:17.11-bookworm@sha256:3645570cccdfa447589da9f57dd740faa29b30938e861289a5574b6ca6b03826`

The verification runner requires **257 tests**, including **132 PostgreSQL tests**:
all 159 existing tests, 19 new unit tests, 33 lifecycle PostgreSQL tests, the original 16 archive
PostgreSQL tests, and 30 archive-completeness regressions. All original 227 tests
remain required. Missing groups, skips, failures, errors, expected failures or
unexpected successes fail verification. Future test changes must update exact counts.
No workflow is dispatched or branch published during this assignment.

Local verification uses the existing Docker tooling and the exact pinned image,
with an explicit external local harness that substitutes a local-context check.
It does not impersonate GitHub or change the committed hosted-runner guard. The
container, volumes and temporary generated credentials are removed in cleanup.
SQLite is not used. Final counts and checks are in the separate review evidence.

## Security assessment and unresolved decisions

The proposal remains unsuitable for confidential or operational use. In particular:

- Identity, MFA/service assertions, policy authority, approvals and HMAC custody are
  synthetic fixtures. Production requires separately approved individual MFA accounts,
  short-lived service identities, durable evidence verification, and independent policy
  administration, approval issuance, signing custody, encryption custody and audit review.
- PostgreSQL RLS reinforces trusted backend scope; credentials can set their tenant
  context. The backend is not a sandbox against arbitrary privileged Python/SQL.
  Direct database credentials must never be exposed to users.
- Approval rechecks use a SERIALIZABLE snapshot and trusted in-process authority;
  globally linearizable revocation and external authority outage behavior remain a
  separate production design. Restored historical evidence grants no current authority.
- Complete synthetic snapshots do not establish production backup, PITR, encryption,
  key recovery, availability, immutable storage, recovery objectives or disaster recovery.
  Signing keys are never exported; restoration requires the same separately trusted
  ephemeral fixture custody. Independent durable signing-key custody remains unresolved.
- Integrity verification cannot establish an external, independently witnessed history
  against an actor who controls all source data, schema and signing custody. Production
  needs separate checkpoints/immutability and an independently administered audit trail.
- Operational, audit, backup and legal-hold retention must be decided independently.
  No retention deletion or enterprise policy is invented. Legacy logs remain quarantined,
  unimported and byte-/metadata-preserved. Denied/rolled-back operations still lack an
  independent durable denial log, as documented in Phase 1B/C.
- Real department names, titles, owners, stage criteria, approvals, escalation owners,
  team permissions, early closure/reopening and opportunity evaluation rules are
  unresolved CEO decisions. The strict all-stage synthetic approval sequence does
  not choose a real organizational approval structure.
- A confidential registry requires a separately approved protected store/private layer.
  Provider, region, pricing/contracts, confidential-pilot availability, backup/recovery,
  retention and real identity/key custody are unresolved. A synthetic Single-AZ choice
  does not settle confidential availability.
- Local PostgreSQL proof is not remote Actions evidence, a load test, cross-host failure
  testing, or validation of other PostgreSQL versions. Dependencies and action/image
  pins require continued review.

No confidential information, live guest workflow, external provider, CRM, Slack,
email/calendar/Drive/publishing connection, infrastructure purchase/provisioning,
deployment, environment publication or operational pilot is authorized by this proof.
Passing tests are technical evidence only. Commit, push, merge and operational use
remain separate approvals; this assignment ends with an uncommitted CEO review.
