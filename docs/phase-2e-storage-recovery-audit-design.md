# Phase 2E M2 — Storage, recovery, audit and incident-response design

## Status and authority

Baseline: `4f8adb93b1931f06c5819a02779b9107c1f30c8d`, merged PR #16.
Branch: `phase-2e/storage-recovery-audit-design`. Review date: November 12, 2026
(America/Chicago). This is documentation and fabricated tabletop analysis only.
No application, schema, migration, workflow or functional test changes are made.
No executable readiness reporter, infrastructure, key, credential, vendor access,
confidential record or connection is introduced. All seven connectors stay disabled.

The [assessment](phase-2e-production-integration-readiness.md),
[roadmap](phase-2e-roadmap.md), [gaps](phase-2e-security-gaps.md),
[acceptance/rollback plan](phase-2e-acceptance-plan.md),
[CEO decisions](phase-2e-ceo-decisions.md) and
[connector gates](phase-2e-connector-gates.md) remain authoritative.
The merged [identity contracts](phase-2e-identity-session-contracts.md) are
synthetic and process-local, not production login or durable revocation.
M2 does not close a production gate. Technical completeness never grants
organizational authority. The [tabletops](phase-2e-operations-tabletop.md) are
reasoned scenarios, not witnessed operational drills or measured recovery.

## Protected storage and role contract

Mission Control services retain policy/domain authority; PostgreSQL retains their
approved durable records. Browsers, Slack, HubSpot and knowledge systems must not
connect directly to PostgreSQL or mutate grants/approvals outside those services.
HubSpot remains commercial authority, Slack communication, and the proposed
2nd Brain institutional knowledge, not operational truth. No integration is added.

| Boundary | Required future design and denial condition |
| --- | --- |
| Hosting | D04 compares managed private PostgreSQL with self-managed hosting, named patch/backup/on-call owners, supported version, region/residency, tier, budget, exit/deletion and vendor terms. No selection is implicit; retain disposable 17.11 as test-only |
| Network | Private database endpoints and explicit workload-to-DB allowlist; no public ingress, browser route, tunnel or localhost-server rebind. Maintenance/restore access is separate, time-boxed and audited; deny unexpected peer or path |
| TLS | Verify certificate chain, expiry and expected hostname using approved trust roots; require encrypted application, replication and backup transit. No insecure fallback or disabled verification; private networking alone is insufficient |
| At-rest encryption | Primary, replicas, snapshots, backup objects, temporary restore storage and audit exports require encryption and independent key access review. Encrypted disk alone does not prevent authorized query misuse |
| Runtime role | Non-owner, non-superuser, no BYPASSRLS, no role creation/schema mutation/backup administration/key administration. Grant only reviewed functions/tables and action-specific privileges; constrain search path, connection limits and transaction/statement deadlines |
| Migration role | Separate controlled identity, reviewed schema artifact and maintenance window; no automatic migration on startup. Elevated access expires; independent review checks RLS, grants, archive coverage and rollback compatibility |
| Backup role | Minimum supported backup/replication capability, separate storage writer with no delete/retention override. Broad physical backup contains all tenants: classify and restrict it accordingly; never offer it as tenant export |
| Restore role | Isolated destination only, separate from runtime and business approver; no default production endpoint switch or external egress. Restore authority does not confer data-reading or restart approval |
| Tenant isolation | Preserve forced RLS, current grants, tenant/resource checks, CAS, revision/approval bindings and rollback. Bind tenant server-side; reset and verify pooled context before reuse. Unknown context, owner bypass or unavailable authorization denies work |

A future production authority/schema needs separate review; never relabel real
records as synthetic or remove existing synthetic constraints. No new database or
parallel registry is proposed. Current archive completeness covers 34 existing
tables only; any later schema addition must revise the coverage manifest and tests.

## Credential, signing and encryption custody

D01/D03 must name separate signing, encryption/secret, platform and independent
review roles. Use provider-neutral managed vault/KMS/HSM references as a design
option, not an installed service. Per-environment workload identities should obtain
short-lived scoped access where supported. No shared CEO key, raw secret in Git,
transcripts, browser, domain payload or CI output. Key administration, use, export,
deletion and recovery permissions must be independently reviewed; merely naming
two roles does not prevent one administrator from granting both.

Signing and encryption have separate purposes and lifecycles. Retain authorized
historical verification keys across rotation; revoked issuers cannot issue fresh
proof. Recovery must preserve decryption for retained backups without exposing key
material to restore operators. Dual-controlled recovery/deletion and immutable
custody access records require later witnessed testing (AT-04). Vault/key outage,
unknown key version, expiry or unavailable reviewer denies dependent operations.
Existing synthetic HMAC is not independent production signing or backup encryption.
No key material or live custody service is created in M2.

## Backup, recovery and evidence contract

The following are **unapproved sizing proposals**, not settings or measured SLOs:
continuous WAL capture with verified shipping age below a proposed 15-minute RPO;
daily full/base backup with incremental/WAL recovery as supported; 35-day encrypted
PITR retention; RTO at most four hours; 99.9% monthly production availability.
D04 must approve feasibility, region, cost, peak workload, recovery point semantics
and service window. D06 must reconcile retention, legal holds and deletion;
D05 must own failures/alerts. No supported cadence or durability is assumed from
an unselected provider. Failover is separate from PITR; JSON export is not backup.

Backups require encrypted independent storage, immutable/versioned copies where
approved, integrity manifests, restricted deletion and tested key availability.
Document a same-region and independent failure-domain option; approve residency
and additional cost before choosing cross-region replication. Track capture time,
last verified recoverable point, schema/version, manifest digest, WAL continuity,
key-version reference, tenant classification, custody owner and retention/hold.
Do not include raw keys or personal records in a public evidence packet.

Future isolated restore procedure:

1. Incident commander freezes admission and any future dispatch; preserve source
   media, immutable audit references and the last known commit/receipt watermark.
2. Independent recovery witness approves a bounded restore point and checks
   manifest, backup integrity, WAL chain and key availability. A failed check
   quarantines that copy; do not overwrite evidence or use an unverified fallback.
3. Restore executor uses a new isolated destination with outbound dispatch denied,
   no automatic application startup and reviewed role/network restrictions.
4. Validate full schema, constraints, extensions/version compatibility, tenant/RLS
   enforcement, grants, policy revisions, identity dependencies, approvals,
   append-only history, archive coverage, domain audit, intentions and receipts.
   Future tables must be included explicitly; missing coverage blocks restart.
5. Compare recovered state to independently retained checkpoints and receipts.
   Record missing intervals, corruption, authorization changes and external
   uncertainty. Existing ephemeral identity sessions cannot be recovered as valid
   sessions; require a new approved authentication boundary, not resurrection.
6. Reconcile outcomes before replay. Recovered old grants/approvals do not become
   current merely because they were in a valid backup. Quarantine disagreement;
   invalidate stale authority and require new exact revision-bound review.
7. Witness records proposed versus actual recovery point, elapsed time, data loss,
   checks and failures. Production RPO/RTO claims require measured hosted drills.
8. Independent security/business and recovery reviewers attest reconciliation;
   the named restart authority approves exact build, scope, data point, policy,
   operating window and stop criteria. Absent authority means continued denial.

A restore does not undo external effects. Future connectors must stay stopped
until their independent receipts are reconciled; never automatically redispatch
on startup, receipt loss or rollback. Unknown outcomes are quarantined. External
compensation is a new human-approved action, not an assumed inverse operation.
No dispatcher or receipt persistence is implemented by this document.

## Audit correlation, custody and failure behavior

Future minimized event records should bind an event/operation reference, exact
build and contract revision, server-held subject/tenant reference where permitted,
authorization decision and lease revision/ordering reference, policy revision,
approval reference/digest, target and expected/committed revision, inactive
execution-intention reference, receipt/outcome reference, fixed reason code and
UTC time. These are a proposed correlation contract, not new persisted fields.
Do not log session IDs, cookies, tokens, CSRF, raw approval proof, directives,
full payloads, hidden records, provider output or rejected values.

Identity admission, authorization lease, business approval, domain commit,
execution intention and external acknowledgment are distinct events. A lease is
not approval; an allowed journal entry does not prove a domain commit. Existing
gateway lease ordering allows already-admitted work to finish before a waiting
revoker returns. Preserve that contract; do not claim instantaneous cancellation.
A future durable correlation mapping must not expose ephemeral authentication
references or turn public fixture IDs into credentials.

Require transactional domain audit with domain writes and independently restricted,
tamper-evident off-host custody for security events, integrity checkpoints, clock
quality, access reviews and deletion/hold records. Same-process signatures do not
provide independent custody. On required audit-write failure, deny the dependent
mutation and roll back before commit. If delivery acknowledgment or independent
export fails after commit, record uncertainty via an approved durable design,
freeze affected work and reconcile; never claim a committed write rolled back.
No silent drop, raw-payload fallback log or audit-failure retry loop.

Candidate retention is 90 days searchable plus one additional immutable year for
minimized security metadata, pending D05/D06 approval. Retention is class-specific;
legal holds override scheduled deletion under reviewed authority. Backup/vendor
copies and minimized audit have separate deletion/hold implications. Do not alter
legacy logs or infer permission to import them. Evidence preservation uses bounded
references/digests and authorized isolated custody, not indiscriminate copying.

## Monitoring and incident lifecycle

Alert thresholds below are proposals requiring D04/D05/D09 decisions and named
primary/backup responders. No alert integration or monitoring process is installed.

| Signal | Candidate threshold / response needing approval |
| --- | --- |
| Audit write/integrity failure, tenant isolation failure, unexpected credential privilege | First verified event: deny affected work and page the incident/security owner |
| Backup/WAL age, restore verification age | Warn before proposed 15-minute recovery-point budget; breach blocks recovery claims. Daily backup and periodic witnessed restore age budgets must be selected |
| Revoked identity use, failed authorization, policy/approval changes | Every privileged change audited; aggregate denial anomaly threshold and revocation target need identity/security approval, not an invented universal rate |
| DB latency/errors, connection saturation, replication lag, storage growth | Workload-specific warning/critical budgets and window must be benchmarked; no current capacity/SLO proof |
| Future queue age, unknown receipt, destination/scope drift, connector cost/rate | Unknown outcome or destination drift freezes affected dispatch; numeric age/volume/cost limits need D08 and a later connector design |
| Operating coverage | No accountable on-duty responder or expired authorization window: no new admitted operation; escalation cannot grant business approval |

Required named roles (assignments remain blocked under D01): incident commander
owns bounded containment; security lead investigates identity/custody; DB recovery
executor restores; independent recovery witness verifies; data/business owner
adjudicates impact; privacy/legal lead handles notification duties; independently
appointed restart authority approves resumption with security/business concurrence.
No actor may solely execute, witness and approve their own restore/restart or
self-grant access. Deputies need documented delegation and limits. Unavailable
primary and authorized backup means contain and remain stopped, not promote a bot.

Lifecycle: **detect → contain → preserve → investigate → recover → reconcile →
obtain restart approval → review**. Preserve a minimized timeline and original
integrity evidence before remediation. Scope incident access, investigate actual
commit boundaries, and distinguish outage from disclosure. Notification deadlines
are jurisdiction/vendor decisions, not invented universal hours. Revoke/rotate
only through approved custody authority. Recovery is isolated; restart is a new
bounded decision. Post-incident review records root cause, evidence gaps, accountable
remediation, revocation/retention effects and independently reviewed follow-up.
No automatic rollback, destructive cleanup of audit or unapproved production drill.

## Acceptance and evidence map

| Criteria | M2 artifact / review evidence | Remaining proof |
| --- | --- | --- |
| AT-04 | Custody separation, key outage and recovery scenarios TT-03/TT-05 | Selected service, named custodians, witnessed rotation/recovery |
| AT-05 | Runtime/migration/restore boundary and TT-09 revision reconciliation | Hosted least-privilege/RLS/pool/rollback verification |
| AT-06 | Full restore procedure and TT-01–03 | Encrypted hosted PITR, failover and measured witnessed recovery |
| AT-07 | Minimized correlation, audit denial, TT-04 | Independent durable custody, real failure/alert routing proof |
| AT-08 | No admission, class/hold/retention decisions and evidence minimization | Approved lawful fields, vendor terms and deletion/hold verification |
| AT-12 | Unknown outcome TT-06, partial restore TT-09, no automatic replay | Future durable intent/receipt/fencing contract and reconciliation drill |
| AT-13 | Incident roles/lifecycle and TT-05/TT-07/TT-08 | Named staffed responders and measured containment/restart drill |
| AT-16 | Exact baseline, missing-evidence denial, decision register and review inventory | Current independently verified production evidence and separate activation |

## Decision options and explicit blocked status

| Decision | Available options / recommendation | Consequence / current status |
| --- | --- | --- |
| D01/D03 | Assign distinct owners and independent deputies; use independently controlled signing/encryption custody, or defer actions that cannot support separation | No names or custody service selected here; production authority BLOCKED |
| D04 | Managed private PG or explicitly staffed self-managed PG; recommend evaluate managed first, approve region/tier/budget/version and measurable recovery targets | No hosting, key or SLO selection; production storage/recovery BLOCKED |
| D05 | Staffed restricted window or proven 24/7 coverage; recommend restricted window until coverage exists, independent audit custody and tested paging | No service window, thresholds, incident/restart personnel or audit retention approved; operations BLOCKED |
| D06 | Approve exact class-specific retention/hold/deletion and vendor terms, or keep synthetic-only; recommend synthetic-only pending privacy/legal review | No confidential admission or retention setting approved; real data BLOCKED |
| D09 | Fund named engineering/DB/security reviewers and supported-platform/manual AT qualification, or narrow scope/date | Capacity/platform commitments unverified; production support BLOCKED |

D02 production identity and D07/D08 connector permissions/automation remain separate
unresolved dependencies, not implicitly resolved by M1 or M2. November 30 remains
a conditional contract/runbook review target, not launch. No production control is
marked complete from these documents or from historical synthetic test counts.
