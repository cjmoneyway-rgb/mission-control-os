# Phase 2E — HubSpot and 2nd Brain integration-impact assessment

[Assessment index](phase-2e-production-integration-readiness.md) ·
[Connector gates](phase-2e-connector-gates.md).
**Design only; no connection, export, backfill, migration, webhook or index.**

## Ownership and field contract

| Information / decision | Authoritative source | Permitted future derivative | Conflict rule |
| --- | --- | --- | --- |
| Contact/company identity and selected relationship/commercial attributes | HubSpot under the commercial data owner | MC stores approved opaque mapping/projection and source version, not a second full CRM | Commercial owner adjudicates source changes/merges; preserve mappings/history, never silently overwrite MC decisions |
| Deal/pipeline state, commercial commitments, relationship ownership | HubSpot plus its approved commercial governance | Observation can inform a separately authorized MC proposal | A CRM stage is not MC task completion, payment proof or organizational approval |
| MC policy, current grants, decisions/approvals, work status, dependencies and audit | MC domain services with authoritative PostgreSQL persistence | Authorized UI/notification/knowledge excerpts with version and purpose | Current MC policy/revision governs actions; external prose or cached mirrors never wins |
| Discussion, delivery notification and human context | Slack communication record within its own retention policy | Minimal link/reference; authenticated intake proposal if separately approved | Message text, display name, emoji or slash command cannot directly issue MC approval or change policy |
| Approved institutional artifact and its publication/version metadata | Named institutional content owner and original approved source | 2nd Brain curated derivative with citation, ACL, classification, validity and provenance | Expired/revoked/superseded knowledge cannot override live operations; new advice becomes a proposal, not an instruction |

A PostgreSQL row is authoritative storage for its approved MC schema, not an
independent business arbiter. HubSpot remains the commercial record, so a duplicate
CRM/contact register in MC is explicitly rejected. The 2nd Brain is neither an
operational replica nor a shadow registry. No new database/schema is created here.

## HubSpot impact: bounded relationship/commercial projection

**Business benefit:** reference current relationship context without forcing the
CEO to reconstruct it from chat. **First engineering candidate:** an offline,
contract-mocked read-only projection, not live account access. A later sandbox read
requires separate authorization, provider scope verification and admitted data.

Proposed minimal contract to review before code:

- Immutable mapping reference binds MC tenant to approved HubSpot portal/account,
  object type and object ID. External IDs are account-scoped; never trust a browser
  or inbound payload to choose the tenant/portal binding.
- Initial projection candidates are source ID/type, update/version metadata and
  explicitly approved bounded status/association references. Names, emails, phone,
  notes, attachments, financial terms and arbitrary custom properties are excluded
  until separately admitted. IDs can themselves be confidential/linkable data.
- Request only the approved properties where the API permits. If the API returns
  extra fields, the admission design must cover receipt in memory as well as
  persistence and telemetry; filtering after unauthorized collection is too late.
- HubSpot contact → authenticated MC user is **not** an identity mapping. Use
  independently verified IdP subjects. Shared email/display name is not proof.
- A contact can participate in multiple journeys. Separate external entity mapping
  from explicit journey associations; do not invent a one-contact/one-journey rule.
- Retain source timestamp/version and retrieval/verification time; mark stale or
  unavailable projections explicitly. Unknown is not zero or “no relationship.”
- Contact/company merge, deletion/archive, reassignment, duplicate and association
  changes require a defined owner-reviewed mapping/tombstone policy. Never silently
  reparent immutable classifications, approvals or journey history.

### Event, writeback and operational implications

Webhook signatures/replay, ordering, duplicates, account binding and secret
rotation must be verified against current official HubSpot documentation before
any receiver is designed. An authenticated event is an observation, not an
approval. Normalize/minimize it in a separately authorized intake boundary;
reauthorize any resulting MC action against current domain policy and revision.

Do not use MC status to automatically close deals or rewrite commercial fields.
Any future writeback is a new action proposal with commercial owner, exact field
list, expected source version, actor/purpose, human approval and audit/receipt.
Read and write permissions are separate activations; neither is authorized here.
No bulk import, CRM migration, unrestricted synchronization or bidirectional loop.

HubSpot scope alone may permit more records than the business admits. Exact
portal/object/property/record constraints and tenant filtering need application
checks. Plan tier, API version, private-app/OAuth model, rate limits, permitted
properties and sandbox facilities remain unverified. No actual portal was queried.

**Impact on MC:** future versioned mapping/projection/delivery contracts and tests,
not duplicate routing/lifecycle logic. If persistence or receipts need new tables,
independently review migration, retention, export/archive and restore coverage.
The existing synthetic 34-table archive does not automatically cover new data.

**Main risks:** PII/commercial leakage; conflicting systems of record; stale data
misread as fact; broad read scopes; cross-portal collisions; feedback loops;
merge/delete misassociation; no independent receipt after unknown external commit.
Tests AT-08 through AT-12 and AT-15 apply; C0–C6 must pass before any activation.

## Slack impact: communication, never the operating system

An approved future Slack notification may convey a minimized authorized status and
protected MC link to one approved channel. No raw directive, confidential payload,
approval evidence, secret or token in message text, attachments, logs or links.
Check audience membership/sharing and source classification at dispatch time.

Do not put state transitions, policy administration, department ownership or
approval history in Slack as their sole record. A reply/reaction may at most
request an authenticated MC review; the approver must enter the appropriate
verified, step-up-protected MC boundary and approve the exact eligible revision.
Bot possession does not prove the identity/authority of a human sender.

Channel changes and message formatting/link previews can disclose information.
Public-channel posting, DMs, history harvesting, file upload, broad directory
scopes and workflow-builder orchestration are excluded by default. There is no
protected remotely reachable MC service today, so do not publish a localhost link
or tunnel merely to make a Slack notification interactive. A mock notification
is an acceptable November deliverable; a working live Slack bot is not assumed.

## 2nd Brain impact: proposed approved institutional knowledge

The user's proposed role is accepted as a **design constraint**, not evidence of
an implemented system, selected platform or permission to connect it. It remains
out of the implementation roadmap's critical path and out of the recommended next
branch. No exporter, ingestion worker, embedding, vector database, retrieval client
or new connector is implemented or enabled.

### Proposed curation contract, for later review only

An institutional artifact would require source system and opaque source reference,
source revision/content digest, owner, approval/provenance references, publication
version, classification, tenant/audience ACL, permitted purpose, validity/expiry,
review date, supersession/revocation state, consent/rights, retention/hold and
canonical citation target. No approval proof body or confidential content in a
public Git record. Provider/tool choice and the exact admissible content remain
CEO/data-owner decisions, not default permissions.

A source artifact can be approved knowledge without becoming approved executable
policy. For example, an approved retrospective may explain a decision; it cannot
change today's work status or authorization rules. Operational freshness must be
read from MC through an authorized minimized projection, not a knowledge answer.
A proposed policy discovered in knowledge must go through separate formal policy
registration, approval and revision controls before any operational effect.

### Boundary and abuse cases

- Curate only independently approved artifacts; no raw Slack histories, entire CRM
  records, provider output or legacy logs. Do not backfill existing records.
- Enforce source and destination ACL intersection, tenant and purpose on export
  and retrieval. No widened visibility through a shared index or model context.
- Treat retrieved text as untrusted data. Embedded instructions, links or suggested
  tool calls never override policy, grant authority or initiate operational action.
- Every answer needs authorized citations and version/validity. Revoked, expired,
  inaccessible, superseded or conflicting sources cause abstention/escalation,
  not fabricated certainty or automatic policy selection.
- Source deletion, hold, ACL revocation and supersession must propagate to chunks,
  embeddings, caches, indexes, replicas and permitted provider copies; define
  revocation/cache windows and verify erasure. Embeddings are not anonymization.
- Any model prompt containing retrieved content requires its own approved outbound
  field/purpose/provider-processing review. Existing SDK safety gating is not a
  production data-loss prevention or vendor-retention control.

### Duplication/retention decision

Prefer approved source references and bounded curated derivatives to another full
content repository. Decide whether the existing document platform can provide
needed custody/ACL/versioning before proposing new storage. Any later index is a
revocable derivative, not the operational ledger. Provider terms, storage region,
model processing, encryption/custody, rights and retention are unresolved.

## Future coexistence acceptance and rollout boundaries

1. Assign one owner to each fact and action, with a documented conflict/escalation
   rule and no circular synchronization.
2. Review synthetic mapping/envelope samples and deny unknown field/account/tenant
   associations. Do not “test” the design with actual contacts or institutional data.
3. Complete identity, custody, storage, data admission, audit, recovery and C0–C6
   evidence before a separately approved isolated sandbox connection.
4. Begin with bounded read-only action/fields only if later authorized. Add writes,
   notifications, curated export and knowledge retrieval only through independent
   decisions and exact acceptance evidence. Never bundle their activation.
5. Reconcile external outcomes before replay/restart after failures or DB restore;
   kill switches and a new human restart decision are mandatory.

For November 30, the defensible target is an approved ownership/field/provenance
contract plus offline synthetic tests after separate implementation approval.
No live HubSpot writeback, Slack operating system or 2nd Brain implementation is
promised. Missing vendor/owner/legal decisions are explicit gates, not assumptions.
