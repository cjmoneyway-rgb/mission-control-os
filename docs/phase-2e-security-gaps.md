# Phase 2E — Security and production-readiness gaps

[Assessment index](phase-2e-production-integration-readiness.md).
**Production blockers are not planning blockers: the plan can be review-ready
while every operational activation remains denied.**

Findings describe missing production proof/capability, not a claim that a deployed
production system is currently compromised. This phase performs source/metadata
inspection only; no penetration test, hosted configuration inspection, dependency
installation/audit call, restore drill or live security assessment is represented.
Existing synthetic tests are useful regression assets, not production certification.

Severity: **Blocker** prevents any production/admitted-data use; **High** prevents
related connector/action activation; **Medium** requires an explicit constrained
operating decision and compensating proof; **Low** is review/documentation follow-up.
Unknown ownership or evidence fails the corresponding gate; it is not a waiver.

## Existing twelve-control mapping

Reuse the exact [Phase 1E control vocabulary](phase-1e-production-readiness.md).
Do not treat the synthetic readiness package's digest checks as evidence that
real provider, human or operational controls exist. Existing operational denial
remains unconditional and unchanged.

| ID / readiness control | Observed baseline and production gap | Severity | Proposed accountable role / proof to close | Acceptance IDs |
| --- | --- | --- | --- | --- |
| G01 `provider-contract` | No selected hosted service/product/tier/region, approved DPA, retention/training/subprocessors, SLA, cost or exit/deletion contract | Blocker | CEO accountable; platform owner + legal/privacy reviewer verify current terms, region, support/exit and approved budget. Vendor “compliant” claims alone fail | AT-08, AT-16 |
| G02 `protected-storage` | Local synthetic Unix-socket PG, forced RLS and constrained synthetic roles; not a hosted encrypted/HA production configuration | Blocker | Platform/DB owner: private connectivity, certificate validation, primary/replica/volume/backup encryption, deletion protection, scoped DB roles, tenant/pool isolation and independently reviewed architecture | AT-05, AT-06 |
| G03 `identity-mfa` | `SyntheticSession` checks fixture claims, freshness and privileges. Local UI has no human authentication/real MFA/IdP, TLS or production session service | Blocker | Identity/security owner: verified issuer/audience/key lifecycle, individual phishing-resistant MFA, step-up/recovery/offboarding, short-lived machine identity, Secure cookies and central revocation | AT-01, AT-02 |
| G04 `authorization-separation` | Exact synthetic grants/deny precedence and domain checks exist; real department ownership, privileged entitlement lifecycle and production control-plane isolation are unspecified | Blocker | Security/policy owner + department owners: subject/tenant/resource/role matrix, least privilege, grants/reviews/revocation and denied-role combinations, pool/session tests | AT-02, AT-03 |
| G05 `approval-authority` | Revision-bound synthetic proof and self-approval defenses exist; no verified human organizational approver, delegation/limits or production authorization | Blocker | CEO names business approvers and independent reviewers; bind exact action/target/fields/revision/policy/evidence/expiry; revoke/delegate with audit. Technical readiness never issues authority | AT-03, AT-09 |
| G06 `key-custody` | `SyntheticEvidenceCustody` generates process-local HMAC; not durable asymmetric signatures, nonrepudiation, KMS, encryption or recoverable historical custody | Blocker | Separate signing/encryption custodians + security reviewer: managed KMS/HSM design, key access separation, rotation/revocation, retained verification keys, recovery/deletion dual control and witnessed drills | AT-04, AT-06 |
| G07 `audit-observability` | Gateway records authorized attempts via injected sink; local fixture sink/counters are bounded in memory. Domain audit is transactional; CLI retention view preserves source. No independent durable security telemetry/alerts/on-call | Blocker | Operations/security owners: durable denied/allowed/privileged events, transaction/delivery correlation, restricted tamper-evident off-host custody, redaction/retention, alert routing and response evidence | AT-07, AT-13 |
| G08 `backup-recovery` | Complete 34-table synthetic archive/reconciliation/rollback tests exist. JSON export and same-custody HMAC are not encrypted production backup, independent checkpoints, PITR, failover or measured RPO/RTO | Blocker | DB/recovery owner + independent witness: encrypted PITR/backup, isolation/immutability, key recovery, scheduled restore/failover and receipts/outbox replay reconciliation | AT-06, AT-12 |
| G09 `retention-legal-hold` | Existing minimized audit/retention views do not supply an approved real-data schedule, legal hold or deletion authority across replicas/backups/vendors/knowledge caches | Blocker | Records/privacy/legal owner: per-class schedule, hold precedence, deletion and evidence-minimization policy; test propagated erasure without rewriting legacy logs or historical approvals | AT-08, AT-15 |
| G10 `incident-response` | Local stop verifies its own process and cleans normal/graceful failures. No production on-call, independent incident custody, vendor compromise playbook or tested end-to-end containment/recovery | Blocker | Named operations incident commander + security/business contacts: service window, escalation/notifications, kill switches, restore and credential compromise tabletop/drills | AT-07, AT-12, AT-13 |
| G11 `data-admission` | Transport only admits synthetic classification and opaque fixtures. No approved real field list, subjects/consent, recipient/region/purpose policy or confidential handling | Blocker | Data owner + privacy/security reviewer + CEO: exact field/account/tenant/recipient/classification/retention matrix and signed admission; reject prohibited content before persistence or outbound processing | AT-08, AT-10, AT-15 |
| G12 `pilot-operating-plan` | Existing plan contracts are explicitly synthetic/inactive and cannot authorize launch. No actual participants, allowed actions, owners, limits, stop criteria or rollback approval | Blocker | CEO + accountable pilot operator: one bounded tenant/journey/action set, named participants, time/cost/volume limits, current complete readiness evidence and separately signed launch decision | AT-09, AT-12, AT-16 |

## Additional integration/control-plane findings

| ID | Gap | Severity and required response |
| --- | --- | --- |
| G13 | Inactive outbox intention is a transient response, not a persisted delivery ledger; no dispatcher, webhook verification or authoritative delivery reconciliation | High: no outbound action. Future design must version schema/archive and add atomic intent/receipt, fencing, bounded retries, revocation and unknown-outcome handling before any transport |
| G14 | Production ownership and permissions for seven vendor accounts/products are unknown | High: every connector stays disabled; exact account, tenant, direction, field/scopes and audit review required individually |
| G15 | Broad SDK range and existing manual synthetic CI are not a production supply-chain/release service | High: reviewed lock/SBOM/license/vulnerability process, pinned release artifacts, attestations, separation of deployment approvals and reproducible synthetic regression evidence before deployment |
| G16 | Synthetic local UI is intentionally plain HTTP, process-local and not hardened/qualified for a production multiuser service | Blocker: never publish/rebind/tunnel it; independently review TLS/session/network/process design without disabling existing local restrictions |
| G17 | Manual assistive-technology/macOS qualification and real workload capacity/SLO tests are absent | Medium for bounded internal evaluation, blocking any claim of supported production platform/accessibility/SLO until qualified |
| G18 | No selected 2nd Brain product, provenance/ACL/retention contract or knowledge publication authority | High: assessment only; no client/export/index/embedding/retrieval implementation or confidential knowledge admission |

## Role ownership and separation of duties

All titles below are proposed responsibilities; **no named human assignment exists
by implication**. CEO decision D01 must name primary, backup and independent
reviewer. A service account, model, integration bot or system administrator cannot
stand in for an independent human business approver.

| Responsibility | Allowed design scope | Forbidden combination or bypass |
| --- | --- | --- |
| Business/data owner and department owner | Approve field purpose/visibility and propose/own bounded work; attest real business outcomes | Cannot unilaterally grant own policy permissions, issue own approval, deploy authority or infer approval from a chat message |
| Business approval issuer / delegate | Approve exact eligible revisions within explicit delegation, limits and expiry | Cannot approve own authored proposal; no blanket future revisions/recipients; delegation cannot exceed issuer authority |
| Policy/security administrator | Reviewed grants, tenant/role mapping, deny rules and revocation; independent change review | Cannot use policy changes to approve own transaction, combine control-plane rights into a universal super-role or bypass domain checks |
| Application workload identity | Narrow service operations tied to verified user/action or an approved machine purpose | No human impersonation, approval issuance, migration, secret administration or cross-tenant default grant |
| Signing custodian | Govern signing operations, algorithms, audit, verification-key lifecycle and revocation | Separate from encryption custody and business approval; never export signing private key into application/CI |
| Encryption/secret custodian | Manage access to encryption keys and vendor credentials under dual review | No business approval; no unrestricted data-plane decrypt/export or sole irreversible key deletion/recovery authority |
| DB/platform operator and migration/restore executor | Reviewed maintenance, least-privilege runtime/migration/backup/restore roles; JIT break-glass | Runtime is never schema owner/superuser/BYPASSRLS; operator access is not permission to inspect confidential rows or self-approve restore |
| Independent auditor/recovery witness | Minimized events, access reviews and witnessed restore/reconciliation | Read-only scope; no policy/approval/key/deployment mutation or raw secret/payload access |
| Incident commander | Bounded containment/dispatch stop and escalation; evidence preservation | Emergency actions do not grant business authority or permit unreviewed data export; time-boxed, dual-reviewed break-glass must be audited |

Authorize an action only when subject, tenant, department/resource, classification,
purpose, revision, dependencies, current evidence and policy all permit it. A role
label alone is insufficient. Human grant changes/offboarding must invalidate active
sessions and pending deliveries within an approved revocation window. “Small team”
is not an automatic separation-of-duties exemption; unresolved staffing blocks the
relevant action. Technical implementation and approval should have distinct actors.

## Secret, API-key and signing-key custody requirements

Use per-environment/per-connector identities and vault/KMS references, not copied
CEO tokens, shared service credentials, browser storage, `.env` in Git or CI output.
Prefer workload federation/short-lived tokens where the selected provider supports
it; long-lived refresh/API secrets need encryption, scoped retrieval, expiry,
rotation, revocation and independent audit. No secret value is collected now.

Production signing should use a reviewed asymmetric scheme in managed custody;
verification must survive process restarts and key rotation. HMAC shared-key proof
is not independent nonrepudiation. Encryption and signing keys have distinct access,
rotation and recovery policies. KMS administrators' ability to change IAM is part
of the threat model: role names alone do not create independent custody. Require
dual control for privilege changes, export/deletion/recovery and independent logs.

Test provider-key outage/revocation, compromised refresh token, overlapping key
rotation, historical verification, backup key recovery, denied environment/tenant
access and emergency access expiry. No actual key creation or live rotation in
this phase. A signing key never becomes a business approval authority by itself.

## PostgreSQL, recovery and operations requirements

Choose managed versus self-managed hosting, service tier, region, data residency,
cost cap and exit path via D04; no provider is assumed selected. Production design
must include verified TLS/private access, patch/major-version lifecycle, HA/failover,
capacity/pool limits, resource quotas, transaction/statement timeouts, connection
identity, row isolation and tested tenant-context cleanup. Preserve CAS, approved
revision binding, constraints, rollback and complete archive coverage.

Candidate RPO ≤15m / RTO ≤4h / availability 99.9% are sizing proposals only.
A restore must be witnessed in an isolated environment, include encrypted backups,
keys, policy/approval/audit history and delivery receipts, and demonstrate no
cross-tenant leakage or automatic re-dispatch. Failover and restore exercise are
separate. Any future schema change (including durable outbox/audit) must update
archive coverage/reconciliation; current 34-table completeness cannot be assumed
for added tables. Never test recovery by importing or altering legacy logs.

Proposed operational signals: denied/invalid identity, privilege/grant changes,
expired evidence, audit unavailability, queue age/retry/unknown outcomes, duplicate
suppression, connector scope/destination drift, DB errors/replica lag/backup age,
restore verification age, latency/capacity, secret/key access and external-provider
rate/cost anomalies. Log references, versions, outcomes and redacted error codes,
not directives, provider output, tokens/cookies/CSRF/proofs or full vendor bodies.

Candidate retention for decision: 90 days searchable security metadata and one
additional immutable year; 35-day encrypted PITR window. These are not approved
settings. Data-class record retention, vendor copies, legal holds and deletion
proof need independent schedules; missing duration/owner means no admission.
Audit append-only does not mean retain all payloads forever or ignore erasure law.

On-call, incident commander, containment authority, legal/privacy notification
contacts and service window must be named. Exercise compromised identity/token,
wrong-recipient disclosure, tenant leak, audit failure, DB loss, vendor outage,
backup/key loss and rogue knowledge input. Stop dispatch/admission first, preserve
minimal evidence, revoke scoped credentials under authority, reconcile external
side effects, recover in isolation and require a new human restart decision.


## Explicit prohibited-data boundary

Now: synthetic fixtures only; no real business, contact, relationship, commercial,
organizational or institutional records may enter the application in this phase,
even if an operator considers them public or prefixes them with `syn-`.

Never place raw passwords, API/signing/encryption keys, MFA/recovery codes, session/
refresh/CSRF tokens, raw approval evidence or hidden cross-tenant records in
business payloads, model prompts, Slack messages, knowledge indexes or review
transcripts. Secret custody is a separate restricted control plane, not domain
content. Proposals must not reveal private rejected payloads or internal policy
material to a broader audience.

Initial future pilot proposals exclude payment-card/government identifiers,
biometrics, health/children's records and privileged HR/legal material by default.
Any exception needs its own lawful-purpose, jurisdiction, retention, vendor and
access review and explicit CEO admission; generic consent or a model safety flag
is insufficient. Do not derive synthetic fixtures by copying confidential records.
Opaque IDs, embeddings, audit metadata and combinations that identify people are
classified data, not automatically anonymized content.

A production readiness/evidence issuance contract is itself future reviewed work.
Reuse the twelve control names and invariants, not the synthetic package's claim
of real authority: current contracts accept only inactive synthetic records and
cannot issue production authorization. Real evidence custody, reviewer identity,
artifact verification and validity enforcement must be separately designed and
proved before any operating approval.

## M2 evidence disposition

The [M2 design](phase-2e-storage-recovery-audit-design.md) and
[tabletops](phase-2e-operations-tabletop.md) describe G02/G06–G11 and their
AT-04–08/AT-12/AT-13/AT-16 dependencies. They are paper analysis only.
G03/G04 retain production gaps despite merged synthetic identity contracts.
No severity is downgraded, production gate closed or external transport added.

## M4 evidence reconciliation — no severity reduction

The [M4 review](phase-2e-readiness-evidence-review.md#gap-triage-and-unresolved-ceo-decisions)
preserves G01–G18 and D01–D09 production dispositions. Synthetic implementations,
local historical test results and M2 paper scenarios do not close custody, real
identity, protected hosting, independent audit/recovery, admission or staffing gaps.
Missing/expired/conflicting evidence remains unavailable, stale or blocked rather
than being converted into production approval by a combined report.
