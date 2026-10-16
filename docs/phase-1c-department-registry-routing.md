# Phase 1C: synthetic department registry and inactive routing

Review proposal on `phase-1c/department-registry-routing`, based on merged main
`9d5f3a2`. Nothing in this proposal authorizes confidential records, operational
routing, external processing, deployment, or the pilot. No new application, CLI,
engine, provider, inbox, or external integration is created.

## Implementation and information sequence

The existing Phase 1B synthetic identity, MFA, policy, evidence custody, PostgreSQL
transaction, migration ledger, and minimized security-decision mechanisms remain
the foundation. `RoutingStore` extends `LocalSyntheticStore`; its opt-in transaction
subclass adds registry/routing operations. Normal application imports and startup
do not load the extension, run migrations, or generate packets.

1. An individually authenticated synthetic policy administrator registers exact
   synthetic reference bindings. Executive references bind to synthetic subjects;
   team references bind to an executive. Unknown references fail closed.
2. A separately authorized writer appends department and rule revisions. Canonical
   names and aliases share one tenant-scoped namespace. Names remain reserved to
   their original department even after an alias disappears from a newer revision.
3. A distinct approval issuer approves a persisted, current department or rule
   revision. Evidence binds tenant, kind, reference, revision, content digest,
   issuing subject, policy revision, validity interval, and ephemeral signing key.
4. A synthetic intake contains only opaque references and classifications, never
   a conversation, directive, or confidential document. The deterministic routing
   simulation verifies current policy, latest rule and department revisions,
   resolved references, preconditions, escalation conditions, and all approvals.
5. One transaction persists the immutable intake, one inactive packet per recipient
   department, exact foreign-key links, hash-linked journey events, CAS heads,
   minimized security decisions, and the idempotency receipt. Exceptions, caught
   public-operation failures, or omission of explicit commit roll everything back.
6. Authorized readers request separate executive, team, command, control, or
   governance projections. An individual responsible executive must explicitly
   authorize team visibility; central routing cannot make internal assignments.
   Even executive distribution is an inactive visibility proposal, not a live task.
7. Later synthetic packet revisions may add outcomes/handoffs and derive a current
   classification. Original intake classification, source, executive/recipient,
   exact registry/rule versions, and historical packet versions cannot be replaced.
   Prior outcome/handoff references cannot be removed from subsequent revisions.

Escalation conditions stop simulation for a separate decision; they never send a
notification. No default rule or implicit fallback exists. All packets and rules
remain `inactive`, even when the synthetic technical approvals verify.

## Public synthetic schemas

All contracts have `tenant_reference`, positive exact `revision`, `schema_revision`
fixed to 1, state fixed to `inactive`, and a SHA-256 `content_digest` over canonical
content excluding the digest itself. JSON decoding rejects duplicate keys, missing
or unknown fields, malformed sequences, and unsupported states. References use a
restricted `syn-` token syntax; this is a fixture boundary, not a confidential-data
classification service. Real information must never be disguised with a prefix.

| Contract | Fields beyond the common envelope |
|---|---|
| Department | Opaque `department_id`, `canonical_name`, `aliases`, `executive_reference`, `team_references`, `mandate`, `information_received`, `information_produced`, `escalation_reference`, `visibility_reference`, `approval_reference` |
| Rule | `rule_id`, `classification`, `preconditions`, `recipients` (department ID, exact revision, digest, executive reference), mandatory command/control/governance visibility references, fixed `output_contract`, `required_action`, `escalation_conditions`, exact policy reference/revision, approval reference |
| Intake | Immutable `event_id`, `original_classification`, `fact_references`, `source_reference`; revision is always 1 |
| DepartmentPacket | Opaque `packet_id`, source event, permanent original and derived current classification, responsible executive, one recipient department, required action, dependencies, priority, decision/approval reference, visibility references, outcomes, handoffs, exact registry revision/digest, rule reference/revision/digest, idempotency reference |

A multi-recipient rule records the responsible executive separately for each
recipient rather than inferring one executive for all departments. The packet ID
is deterministic over tenant, intake ID, and department ID. It is independent of
retry keys, so changing a key cannot duplicate an intake. Rules cannot address a
team as a department or add a team-assignment field to the packet schema.

Canonical names are already normalized restricted tokens. Uppercase, whitespace,
Unicode lookalikes, and free-form names are rejected rather than normalized into
potentially colliding names. Names in distinct tenants remain independent.

## Visibility versus authority

`command` represents CEO Command Center visibility; `control` represents Mission
Control visibility; `governance` represents Governance visibility. `executive`
models the responsible VP/Director reference without resolving any real title.

Every capability requires an exact-resource grant from the separately trusted
synthetic authority and a matching persisted policy revision. Existing deny
precedence, MFA freshness, individual-account requirements, service TTL limits,
revocation checks, and separation of privileged duties still apply.

| Audience/operation | Additional boundary |
|---|---|
| Responsible executive | Exact executive visibility grant, human session, executive-to-subject binding |
| Internal team | Exact team visibility grant, matching executive boundary, prior executive distribution event for that exact packet revision |
| Command, control, governance | Separate exact audience grants; oversight projections omit required action, mandate, teams and approval evidence |
| Central writer/service | Explicit registry/rule/packet capabilities; no implicit audience grants or team-distribution authority |
| Approval issuer | Exact issue/revoke authority; cannot approve own authored revision; current issuing authority is checked during use |
| Policy administrator | Reference registration and policy persistence; no implicit approval, data-writing, visibility, or activation authority |

Signing custody and encryption custody remain distinct existing duties. Neither
visibility nor a verified synthetic approval grants assignment, activation,
external-processing, or provider permissions. Evidence is checked again on clean
transaction exit. Missing, stale, revoked, expired, mismatched, or unverifiable
evidence blocks simulation and exact retries. A new department revision makes a
rule pinned to its old revision stale; a new rule revision requires its own exact
approval. Approval references never authorize an unapproved change.

## PostgreSQL persistence extension

`0001_synthetic_foundation.sql` and the approved 14-entity logical model are unchanged.
Forward-only `0002_department_routing.sql` adds ten tables inside the same `mc_syn`
schema; it does not replace the existing registry/journey persistence or create a
second tracking application. The richer public synthetic contracts extend the
minimal Phase 1A/B reference-only contracts without changing their meaning.

| Table | Purpose |
|---|---|
| routing_records | Department, rule, intake and packet revisions; tenant/kind/reference/revision composite key; actor and policy FKs; immutable payloads |
| routing_heads | CAS revision heads with exact revision foreign keys and one-step update trigger |
| routing_names | Permanent tenant-scoped canonical/alias claims, linked to first department revision |
| routing_references | Separately policy-administered synthetic reference catalog and executive/team parent bindings |
| routing_links | Packet links to exact tenant-scoped department and rule revisions/digests and immutable source intake |
| routing_evidence | Exact record-bound evidence, independent issuer, validity interval and synthetic signing proof |
| routing_revocations | Append-only evidence revocation records |
| routing_events | Ordered, hash-linked intake and packet journey plus executive visibility decisions; inactive only |
| routing_journey_heads | CAS sequence heads with exact journey-event foreign keys |
| routing_receipts | Transactional operation/key/payload-digest/result bindings |

All ten tables force tenant RLS and `dataset='synthetic'`. Runtime gets SELECT and
INSERT; UPDATE is limited to CAS heads. Immutable-history triggers prohibit
UPDATE/DELETE of records, evidence, reference/name claims, receipts and events.
No runtime DELETE, TRUNCATE, DDL or bypass privilege is introduced. Database checks
reject active states, revised intakes and changed original packet identity.
Tenant-scoped composite foreign keys include exact referenced digests. A deferred
constraint trigger requires packet links at commit and checks original intake
classification, department/executive, rule membership, action and oversight fields. Packet
revisions and event chains retain predecessors. Application validation separately
checks nested contracts, reference resolution, responsibility and approvals.

Migration application uses the original advisory lock and migration ledger. The
baseline checksum is checked first, then the extension is applied transactionally
with its own immutable checksum. A failed extension rolls back its tables/ledger
entry; an already installed baseline remains intact. There is no down migration,
seed import, startup migration, production connection option or legacy-log import.
Only the explicitly approved disposable PostgreSQL environment may run this proof.

## Verification and workflow maintenance

The full suite includes the original 95 tests, 21 new contract/security tests, and
43 new PostgreSQL routing tests: **159 total, including 53 PostgreSQL tests**.
The PostgreSQL runner requires both original and new PostgreSQL groups to execute;
skips, failures, errors, unexpected successes and expected failures all fail CI.
The exact totals are deliberately explicit: future tests must update these gates.

Local validation uses the pinned official PostgreSQL 17.11/bookworm image in a
disposable existing Docker environment, with loopback-only access, generated
synthetic credentials, separate administrative/runtime identities, and SCRAM
before testing. The external local harness explicitly substitutes a local-context
check; it does not impersonate a GitHub-hosted job or weaken the committed guard.
Containers, volumes and generated credential files are destroyed in cleanup.
SQLite is never used. See the separate verification report for final results.

Tests cover contract parsing/digest binding, name/alias collisions, permanent name
reservations, independent tenant namespaces, approvals/revocation/expiry/custody,
self-approval, visibility versus authority, individual executive/team boundaries,
multi-recipient generation, source-classification permanence, duplicate/colliding
intakes, exact retries, concurrent intake and registry writes, stale revisions,
transaction/migration rollback, inactive-state/history constraints, RLS, composite
foreign keys, absence of engine/provider delivery, minimized audit, and baseline
backup-format rejection on extended databases. All existing fail-closed tests run.

Official action releases were fetched from their official Git repositories; their
`action.yml` files declare native `node24`:

| Action | Official source/release | Exact pinned commit |
|---|---|---|
| Checkout | https://github.com/actions/checkout/tree/v6.0.1 | `8e8c483db84b4bee98b60c0593521ed34d9990e8` |
| Python setup | https://github.com/actions/setup-python/tree/v6.1.0 | `83679a892e2d95755f2dac6acb0bfd1e9ac5d548` |

The workflow retains only `workflow_dispatch`, standard `ubuntu-24.04`, and
`permissions: contents: read`. It references no repository/organization/environment
secrets, publishes no artifacts or caches, has no deployment or operational
integration, and uses job-generated synthetic credentials and the unchanged pinned
disposable PostgreSQL image. No workflow is dispatched during this uncommitted
assignment; local success does not establish remote-run success.

## Remaining risks and unresolved CEO decisions

- This is a synthetic technical foundation. Actual department names, executive
  titles, personnel/ownership assignments, information taxonomy, mandates,
  escalation ownership, team grants and approval gates are **unresolved**.
- Confidential records require a separately approved private repository or protected
  data store. A public repository must never hold the confidential registry layer,
  complete Phase One specification, credentials, personnel records, or real intakes.
- Production provider/region, availability (including a separate confidential-pilot
  availability decision), cost, contractual controls and recovery objectives remain
  **unresolved**. Synthetic Single-AZ choices do not settle pilot availability.
- Synthetic sessions and policy are trusted in-process fixtures, not an identity
  provider or distributed policy service. Production requires individual MFA
  identities, short-lived service credentials, and independently administered policy,
  approval issuance, encryption custody, signing custody and audit review.
- Runtime credentials do not sandbox arbitrary privileged Python/SQL code. The
  backend can set its tenant context; direct database credentials must not be
  exposed to end users. RLS complements the trusted application authorization layer.
- Approval HMAC keys are ephemeral, not durable production signatures or evidence
  custody. Database transactions use SERIALIZABLE snapshots; commit rechecks do not
  promise globally linearizable revocation against a distributed authority. A
  production revocation/freshness protocol requires separate design and tests.
- Existing v1 synthetic export/restore is intentionally blocked when Phase 1C tables
  exist, even if accessed through the baseline store. It must not silently omit new
  records. A complete reviewed archive/restore format, encrypted backups, restore
  exercises and disaster recovery remain prerequisites to confidential use.
- Retention for operational records, audit, backups and legal holds requires
  separate decisions. No destructive retention or enterprise policy is invented.
  Legacy logs stay quarantined, byte- and metadata-preserved, and are never imported.
- Minimized successful security decisions are persisted in the transaction. Denied
  and rolled-back operations still need separately reviewed independent incident
  logging for production. There is no payload logging or external telemetry here.
- Throughput, failure injection across hosts, multi-process load, PostgreSQL versions
  other than the tested 17.11, and remote GitHub runner execution are not established
  by local correctness tests. Pin updates require future review.

The next step is focused CEO review of the uncommitted diff and technical evidence.
Passing tests do not authorize commit, push, merge, confidential use, integrations,
provisioning, deployment, operational routing, or the Podcast Guest Intelligence pilot.
