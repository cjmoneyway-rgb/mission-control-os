# Phase 1D synthetic routing and lifecycle matrix

All rows describe inactive technical simulation. No actual guest, meeting, research,
interview, production, release, distribution, opportunity, payment or relationship
activity occurs. Persisted stage, classification, action and evidence values are
opaque synthetic identifiers. Human-readable labels below describe the test only.
Real department names, VP/Director titles, owners and approval gates are unresolved.

One source intake retains `syn-entry-class` permanently. Every stage appends an
event, decision, journal links, and inactive Department Work Packets. Alpha and beta
below mean only `syn-department-alpha` / `syn-department-beta`, routed through
`syn-executive-alpha` / `syn-executive-beta`; they imply no real organizational role.

| Stage token | Synthetic lifecycle stage | Current classification | Recipient(s) | Required predecessor |
|---|---|---|---|---|
| syn-stage-01 | Candidate received | syn-class-01 | alpha | None |
| syn-stage-02 | Qualification completed | syn-class-02 | beta | Accepted stage 01 |
| syn-stage-03 | Participation approved | syn-class-03 | alpha | Accepted stage 02 |
| syn-stage-04 | Interview scheduled | syn-class-04 | beta | Accepted stage 03 |
| syn-stage-05 | Research completed | syn-class-05 | alpha | Accepted stage 04 |
| syn-stage-06 | Interview completed | syn-class-06 | beta | Accepted stage 05 |
| syn-stage-07 | Production completed | syn-class-07 | alpha | Accepted stage 06 |
| syn-stage-08 | Release package approved | syn-class-08 | beta | Accepted stage 07 |
| syn-stage-09 | Journal opportunity evaluated | syn-class-09 | alpha, beta | Accepted stage 08 |
| syn-stage-10 | Intelligence opportunity evaluated | syn-class-10 | alpha, beta | Accepted stage 09 |
| syn-stage-11 | Creative assets prepared | syn-class-11 | alpha | Accepted stage 10 |
| syn-stage-12 | Social distribution prepared | syn-class-12 | beta | Accepted stage 11 |
| syn-stage-13 | Relationship follow-up recorded | syn-class-13 | alpha | Accepted stage 12 |
| syn-stage-14 | Speaking opportunity evaluated | syn-class-14 | beta | Accepted stage 13 |
| syn-stage-15 | Revenue or partnership signal evaluated | syn-class-15 | alpha, beta | Accepted stage 14 |
| syn-stage-16 | Journey completed or closed | syn-class-16 | beta | Accepted stage 15 |

For index NN, the test pins `syn-pilot-rule-NN` revision 1 and its content digest,
requires `syn-evidence-NN` as an explicitly registered synthetic evidence fact, and
uses `syn-action-NN`. Rule and department approvals bind exact persisted revisions.
Every event proposal independently requires exact-revision approval from a different
synthetic issuer. This includes participation and release decisions, and is a strict
synthetic proof rule, not a determination of the real CEO approval hierarchy.

Each accepted test event links `syn-pilot-outcome-NN` and `syn-pilot-handoff-NN` to
its packet(s). These are references only; they contain no findings, creative assets,
contacts, monetary values or external destinations. Stage 16 requires an explicit
`syn-completed` or `syn-closed` terminal reference. Early closure, skipped stages,
real approval authority, opportunity criteria and real dependency policies remain
unresolved and are not inferred from this technical sequence.

| Condition | Persistence and routing result |
|---|---|
| Valid next event, current approved registry/rule and exact event approval, all dependencies accepted | Append accepted event/decision, packet(s), handoffs/outcomes, receipts and CAS heads atomically |
| Additional dependency not accepted | Append blocked attempt/decision/receipt, preserve completed-stage head, create no packets or deliverables |
| Retry identical blocked attempt | Return the same explicit blocked result; no new routing |
| Resolve a blocked attempt | Submit a separately identified/reviewed proposal; do not rewrite the blocked event or reuse its receipt as acceptance |
| Invalid order, wrong predecessor, unresolved fact, incomplete rule evidence, missing/revoked/unverifiable approval, stale revision, policy denial | Reject and roll back; no stage advancement or packet creation |
| Duplicate event with a different key, key reused with changed content or version, concurrent stale writer | Reject with conflict; retry the original unchanged request after obtaining current state |
| Terminal stage already accepted | Exact authorized retry may return its old inactive result; further transitions fail |

Command, control and governance mean CEO Command Center, Mission Control and
Governance visibility. Separate exact audience permissions are required. Oversight
views omit action/evidence/outcomes; executive views expose only the existing small
packet projection and required action. A distinct individual department executive
controls team visibility. Central classification/routing cannot assign internal
teams, and visibility never grants approval, activation or external-processing rights.
