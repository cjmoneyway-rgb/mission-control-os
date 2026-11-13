# Phase 2E M2 — Synthetic operations tabletop evidence

## Evidence level and method

[Storage/recovery/audit design](phase-2e-storage-recovery-audit-design.md) ·
[Acceptance and rollback](phase-2e-acceptance-plan.md) ·
[Decision register](phase-2e-ceo-decisions.md).

Baseline: `4f8adb93b1931f06c5819a02779b9107c1f30c8d`.
These are author-reasoned, fabricated paper scenarios reviewed for internal
consistency on November 12, 2026 (America/Chicago). No human operational team
participated, no independent witness signed, and no executable drill, service,
restore, provider access, credential or confidential data was used. References
such as `syn-m2-build` and revisions below are public invented labels, not real
records or authorization. No elapsed recovery time or production pass is claimed.

**Pass** means the written case demonstrates a specified design invariant.
**Conditional-pass** means the case is coherent but depends on unassigned roles,
selected infrastructure or unexecuted proof. **Fail** means the proposed design
violates its invariant. All nine cases are conditional-pass for design only;
all production recovery, activation and restart gates remain blocked.
Role names are required responsibilities, not claims of assigned people.

## TT-01 — Total database loss

- **Fabricated starting state:** `syn-m2-build`, policy revision 7, backup reference
  `syn-m2-backup-a`, independent receipt watermark 40; no enabled connector.
- **Trigger / detection:** primary and replica become unreadable; DB health and
  availability signals identify loss, recovery owner confirms extent.
- **Containment:** incident commander denies admission and dispatch; no new writer
  is pointed at an empty database.
- **Preserve:** manifest/WAL/checkpoint digests, last authorized commit references,
  minimized incident timeline and independent receipt watermark; no payload copy.
- **Roles / approval:** DB executor restores; independent witness checks; security
  and business owners reconcile; separate restart authority must approve.
- **Recovery:** validate backup and keys; restore to isolated storage; verify full
  schema, RLS, grants, audit, policy, approvals, history and archive manifest.
- **Reconcile:** compare recovered revisions and receipt 40 to independent records;
  any missing interval remains explicit; old sessions cannot resume.
- **Restart / rollback:** continued denial until witnessed reconciliation and new
  exact restart authorization; preserve failed destination for scoped investigation.
- **Dependency / result:** D01/D03–D06/D09 and hosted PITR proof missing;
  **conditional-pass**. Maps AT-04–08, AT-12–13, AT-16.

## TT-02 — Incomplete or corrupted backup

- **Fabricated starting state:** `syn-m2-backup-b` claims schema revision 3 and
  complete coverage but lacks an audit segment; digest disagrees with manifest.
- **Trigger / detection:** pre-restore manifest/coverage validation fails.
- **Containment:** witness rejects backup; no partial restore is promoted.
- **Preserve:** original corrupted copy, expected/observed digests, missing-segment
  reference and access timeline in restricted custody.
- **Roles / approval:** DB executor reports; witness rejects; incident commander
  retains containment; independent owners decide whether an older point is eligible.
- **Recovery:** test a separately verified alternate backup in isolation only;
  no rewriting manifest to match corrupt content.
- **Reconcile:** explicitly compare lost interval, policy/approval/audit/receipt
  coverage and external watermark; investigate backup-chain cause.
- **Restart / rollback:** discard no evidence; quarantine failed restore; deny
  restart if any mandatory coverage remains unverified.
- **Dependency / result:** D04 backup options and D05 custody/alert routing absent;
  **conditional-pass**. Maps AT-05–08, AT-12–13, AT-16.

## TT-03 — Missing recovery or encryption key

- **Fabricated starting state:** encrypted `syn-m2-backup-c` names
  `syn-m2-key-version-2`; authorized recovery access is unavailable.
- **Trigger / detection:** approved preflight cannot verify decryption availability.
- **Containment:** stop restore; do not export a key or disable encryption.
- **Preserve:** key-version reference, denied-access reason and custody timeline;
  no key bytes or backup plaintext.
- **Roles / approval:** separate encryption custodian and independent recovery
  witness validate access; DB executor cannot self-grant custody privileges.
- **Recovery:** invoke dual-controlled recovery under a future approved service,
  then validate integrity and historical verification references in isolation.
- **Reconcile:** ensure decrypted artifact matches original manifest and policy;
  custody recovery does not retroactively authorize expired approvals.
- **Restart / rollback:** continue denial if key recovery or independence fails;
  preserve encrypted originals; never claim recovery from unreadable backups.
- **Dependency / result:** D01/D03/D04 custody service and witnessed key recovery
  unselected; **conditional-pass**. Maps AT-04, AT-06–08, AT-13, AT-16.

## TT-04 — Audit-write failure

- **Fabricated starting state:** synthetic request `syn-m2-request-a` proposes
  revision 8 from revision 7; required audit sink cannot append.
- **Trigger / detection:** audit append returns failure; security signal fires.
- **Containment:** deny mutation before commit and retain original revision 7.
  If an independent export fails after an already committed operation, classify
  that different boundary as uncertain export, never pretend rollback occurred.
- **Preserve:** sanitized failure code, operation/build/policy references and
  transaction outcome; no fallback raw request logging.
- **Roles / approval:** application owner contains dependent work; security audit
  custodian investigates; independent business/security restart reviewers approve.
- **Recovery:** restore verified audit capability without deleting denied events;
  correlate preflight attempt separately from committed domain audit.
- **Reconcile:** verify zero partial domain/receipt writes in the precommit case;
  inspect authoritative commit record for the postcommit variant; avoid blind retry.
- **Restart / rollback:** remain denied until integrity/coverage is verified and
  authority signs; do not silently queue unbounded unaudited work.
- **Dependency / result:** D05 durable sink, alert routing and custody unselected;
  **conditional-pass**, not an executed rollback test. Maps AT-05, AT-07–08,
  AT-12–13, AT-16.

## TT-05 — Compromised identity or revoked session

- **Fabricated starting state:** `syn-m2-subject-a` has a synthetic guarded request
  admitted under revision 4; a revoker waits for its existing gateway lease.
- **Trigger / detection:** compromise report or revoked-session use reaches the
  identity/security owner through a future approved signal.
- **Containment:** deny later requests after revocation returns; admitted work may
  finish first under existing lease ordering. Stop affected future dispatch.
- **Preserve:** minimized subject/policy/lease decision and commit references;
  never record session identifiers, raw tokens or rejected evidence.
- **Roles / approval:** security owner scopes revocation; custodian handles any
  separately authorized future credential action; independent business reviewer
  evaluates committed effects; restart authority is distinct from compromised actor.
- **Recovery:** review grant changes and sensitive actions; use a new approved
  authentication boundary, not a recovered old session or manufactured MFA proof.
- **Reconcile:** distinguish admitted/committed from denied work; do not erase
  legitimate audit or claim revocation undid committed effects.
- **Restart / rollback:** deny sensitive work until independently reauthorized;
  compensating domain/external changes need new exact approval.
- **Dependency / result:** D01–D03/D05 production identity/custody unresolved;
  **conditional-pass**. Maps AT-04–05, AT-07, AT-12–13, AT-16.

## TT-06 — Unknown external connector outcome

- **Fabricated starting state:** hypothetical receipt `syn-m2-receipt-u` is missing
  after a hypothetical provider accepted an action. This is a future-design
  counterfactual: all seven actual connectors remain disabled, with zero sends.
- **Trigger / detection:** future acknowledgment timeout cannot distinguish
  external success from failure.
- **Containment:** quarantine the intention; no blind retry or automatic restart.
- **Preserve:** action/target digest, expected revision, approval and idempotency
  references and receipt uncertainty; no full vendor response or credential.
- **Roles / approval:** integration/business owner and independent reviewer
  reconcile; incident commander contains; humans separately approve compensation.
- **Recovery:** future bounded status reconciliation only if independently
  authorized and vendor supports it; otherwise retain unknown state.
- **Reconcile:** compare independent provider receipt and internal ledger; never
  infer success from timeout or promise exactly-once external execution.
- **Restart / rollback:** affected action remains blocked until uncertainty resolved;
  irreversible effects cannot be automatically undone.
- **Dependency / result:** D07/D08, C0–C6 and durable intent/receipt design missing;
  **conditional-pass** for analysis, no transport tested. Maps AT-07–08,
  AT-12–13, AT-16.

## TT-07 — Unauthorized or premature restart

- **Fabricated starting state:** an isolated restored copy passes technical
  checks but has no independent signed restart scope.
- **Trigger / detection:** executor requests resumption using a green health result.
- **Containment:** reject request; technical readiness is not business authority.
- **Preserve:** denied operation reference, exact build/revisions and missing-gate
  code; do not retain raw approval evidence in broad transcripts.
- **Roles / approval:** executor cannot witness or approve own restart; separate
  restart authority needs business/security and recovery-witness concurrence.
- **Recovery:** collect missing evidence and independently review exact data point,
  allowed actions, operating window and stop conditions.
- **Reconcile:** invalidate approval if build, policy, recipient or restored
  revision changes; resolve all unknown receipts before considering resumption.
- **Restart / rollback:** continued denial; no auto-promote, override flag or
  operational-denial bypass is proposed.
- **Dependency / result:** D01/D03/D05 named restart roles unavailable;
  **conditional-pass**. Maps AT-05, AT-07, AT-12–13, AT-16.

## TT-08 — Unstaffed incident window

- **Fabricated starting state:** incident arrives outside a proposed restricted
  service window; both primary and authorized deputy are unavailable.
- **Trigger / detection:** coverage escalation cannot obtain accountable response.
- **Containment:** no new admitted production work; preserve stopped posture.
  This is a future operating policy, not new executable scheduling logic.
- **Preserve:** alert/acknowledgment references, unavailable-role status and timeline,
  without personal contact information in the public packet.
- **Roles / approval:** incident commander/deputy and independent restart authority
  are required; no automatic bot promotion or universal administrator substitution.
- **Recovery:** wait for authorized coverage; investigate backlog and elapsed
  evidence validity before a bounded human review.
- **Reconcile:** reevaluate expired approvals, recovery point and unresolved effects;
  elapsed time cannot renew evidence.
- **Restart / rollback:** continue denial while coverage or independent review is
  absent; reduce service window rather than promise unsupported availability.
- **Dependency / result:** D01/D05/D09 staffing and escalation unresolved;
  **conditional-pass**. Maps AT-07–08, AT-12–13, AT-16.

## TT-09 — Partial recovery with policy/receipt disagreement

- **Fabricated starting state:** restored policy revision 5 permits an action,
  independent checkpoint records revocation at revision 6, and external watermark
  40 exceeds restored receipt watermark 38.
- **Trigger / detection:** post-restore comparison finds two missing receipts and
  stale authority despite internally valid database constraints.
- **Containment:** deny dispatch and restart; do not select the most permissive copy.
- **Preserve:** both checkpoint digests, missing receipt references, policy history
  and restore point; retain append-only audit without rewriting disagreements.
- **Roles / approval:** DB executor investigates with independent witness;
  security owner adjudicates authority; business/integration owner resolves effects;
  separate restart authority approves only fully reconciled scope.
- **Recovery:** reconstruct authorized current policy/receipt state from verified
  independent evidence in isolation; do not fabricate lost approvals or receipts.
- **Reconcile:** validate tenant isolation, complete schema/archive/audit/approval
  history and current grants; quarantine any unresolved external operation.
- **Restart / rollback:** retain denial when authoritative evidence is missing;
  no automatic replay of receipts 39/40 or restoration of revoked sessions.
- **Dependency / result:** D03–D06 independent custody and later durable delivery
  contract unresolved; **conditional-pass**. Maps AT-04–08, AT-12–13, AT-16.

## Result ledger and limitations

Nine documented cases; zero executed operational drills; nine conditional-pass
paper results; zero unconditional production passes. No functional tests run by M2.
Historical 552-test results belong to the merged identity/session baseline and are
not new M2 execution evidence. Actual hosted restore, key recovery, paging, human
response, RPO/RTO, availability and vendor readiness are all unverified.

Each scenario must later bind a reviewed build/environment, current policy/evidence
revisions, named executor/witness/approver, expected versus observed result,
minimized immutable evidence and expiry before operational acceptance. Missing
owners or evidence deny the gate. The CEO can review this design now while all
production/admission/activation gates remain blocked. No legacy logs are copied,
rewritten or used as recovery fixtures.
