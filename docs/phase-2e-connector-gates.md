# Phase 2E — Seven-connector inventory and activation gates

[Assessment index](phase-2e-production-integration-readiness.md).
**Every connector remains disabled; no activation is authorized.**

The exact inventory comes from `CONNECTOR_REFERENCES`/`CONNECTORS` in
[connection_contracts.py](../mission_control/connection_contracts.py). Nine logical
surfaces minus internal Command Center and dashboard yield **seven** connector
descriptors, each `enabled=False`, `state=unresolved`. `Connector.validate()`
requires that state; `transmit()` reaches unconditional operational denial.
There is no transport, OAuth client, webhook receiver or durable dispatcher for
these descriptors. The distinct [OpenAI SDK provider](../mission_control/providers.py)
is a separate guarded code path, not evidence that `syn-chatgpt` is connected.

The 2nd Brain is not an eighth connector or an implemented alias of documents.
A future proposal must define its own destination, permissions, curation and
admission contract even if it eventually uses a document platform. No enum or
connector definition changes in Phase 2E.

## Common activation gates (all mandatory, per connector)

| Gate | Required evidence; missing proof means disabled |
| --- | --- |
| C0 — Business/authority | Named business owner, purpose, field/direction/system-of-record mapping, permitted actions and explicitly excluded actions; exact approved tenant/account/environment |
| C1 — Vendor/data | Current official API/product/plan/scope verification, licensing/rate-limit terms, DPA/subprocessors/region/retention/training/deletion and approved field/recipient/classification admission |
| C2 — Identity/custody | Reviewed production human/service identity, least-privilege scopes plus record/tenant ACL, independent secret custody, rotation/revocation and no shared CEO credential |
| C3 — Safety/approval | Revision-bound human approval for each allowed mutation, step-up where required, policy recheck at dispatch, deny direct webhook/chat/model execution |
| C4 — Reliability/evidence | Approved durable intent/receipt design, duplicate/replay/timeout/unknown-outcome tests, limits/backoff/fencing, dead-letter handling and audit minimization |
| C5 — Operations/recovery | Monitoring, alert recipients/on-call, per-connector/global kill switch, token revocation, reconciliation and witnessed rollback/compensation drill; irreversible-action policy |
| C6 — Bounded activation | All twelve readiness controls satisfied with current real evidence; independent security review; CEO signs exact environment/action/field/recipient/time bounds and stop conditions; separate confidential-data/pilot admission |

These gates are **proposed evidence requirements**, not executable activation
flags and not an instruction to remove `require_operational_authorization()`.
Approval of this assessment or a sandbox design is not approval of production
activation. Offline mocks do not satisfy vendor/security/operating gates.

## Connector-by-connector risk and permission matrix

Permission strings below are illustrative candidate families, not a verified
grant or a request to obtain credentials. Exact scopes must be rechecked against
the selected product/API version and account plan before any later implementation.
Apply resource restrictions in the adapter as well as provider scope; OAuth scopes
alone often grant more records than the approved workflow may access.

| Exact descriptor / current state | Intended purpose and permitted first candidate | Specific risks and dependencies | Minimum proposed permission boundary | Connector-specific activation proof |
| --- | --- | --- | --- | --- |
| `syn-chatgpt` — disabled/unresolved | Model-assisted analysis/drafting of separately admitted content; first candidate is deterministic mocks, then a separately approved isolated synthetic model trial | Product ambiguity: ChatGPT workspace versus OpenAI API; prompt/response confidentiality, retention/training/region, injection, model drift, fabricated authority, cost/latency and tool actions | One approved product/project/model, inference only, project budget/rate limits; no organization admin, broad files, memory, tools or cross-project credentials. Provider-specific API permission names remain unverified | Choose product and owner; exact outbound-field review and vendor terms; adversarial injection/data-exfil tests, output governance, cost caps, safe timeout; model output never grants policy or approval. Existing SDK key/safety boolean is insufficient production evidence |
| `syn-slack` — disabled/unresolved | Approved **communication surface**; first candidate is an outbound minimized status notification to one owner-approved channel, initially mocked | Channel audience expansion, accidental public posting/DMs, link previews, replay/forged interactions, bot overreach, retention/export, chat mistaken for authorization | Candidate bot `chat:write` only to an invited allowlisted channel; no `chat:write.public`, histories, files, DM access, user directory or admin scopes by default. Add interactive/read scopes only under a new action-specific review | Verify workspace/channel binding, audience/retention, destination review, escaped rendering and signed-interaction replay handling if ever enabled; no Slack reaction/message/slash command is a final MC approval. Protected deep links require a future approved service, never a tunnel to localhost |
| `syn-hubspot` — disabled/unresolved | Approved **relationship/commercial record**; first candidate is a contract-mocked read-only projection of selected contact/company identifiers and update/version metadata | Personal/commercial data, cross-portal IDs, broad OAuth reads, merge/delete events, stale associations, writeback overwrites, pipeline/licensing changes, unsolicited CRM migration | Candidate `crm.objects.contacts.read`, `crm.objects.companies.read`; deals read only if separately justified. No write, delete, import/export, owners/admin or unrelated scopes. Exact API/portal permissions and returned properties need verification | Commercial owner approves field/system-of-record map, portal binding, property minimization, merge/tombstone handling and reconciliation. Even IDs are classified data; read-only does not bypass admission. All future writeback requires a separate exact-field proposal and approval |
| `syn-email` — disabled/unresolved | Future human-reviewed communication; first candidate remains offline rendering/recipient validation only | Wrong-recipient disclosure, spoofing, replies/threads, attachments, deliverability and legal/marketing obligations; sending cannot be reliably undone | If ever approved: one service identity, send-only to explicit recipients, no mailbox-wide read/search/admin, no bulk campaign or unrestricted attachments; exact provider not selected | Approved sender/recipients/templates, opt-in/consent and domain requirements, recipient confirmation, dedup, rate limits and irreversibility acknowledgment. Do not infer delivery from a queued request |
| `syn-calendar` — disabled/unresolved | Future proposed meeting/time coordination, not automatic scheduling; first candidate is a mocked availability/hold proposal | Attendee identity/time zone errors, private calendar disclosure, meeting links, spam, conflicting edits, recurring invitations and externally delivered updates | Prefer free/busy only for selected calendars; no event-body/private-calendar read. Write/invite permissions require separate approval for exact calendar/attendees/action. Provider unspecified | Verified participant consent, time zone, ownership and stale-version checks; conflict/duplicate/cancellation tests; humans approve external invitations and updates. No live scheduling by November 30 is committed |
| `syn-documents` — disabled/unresolved | Governed source/artifact references and approved document delivery; first candidate is an offline schema/ACL contract | Broad drive access, inherited sharing, malicious files/macros/links, hidden revisions, rights/consent, download caches, accidental knowledge ingestion | One approved folder/library and specific file/version actions; no organization-wide search/listing, sharing/admin, arbitrary URLs, uploads or writeback by default. Exact vendor not chosen | Document owner/rights/ACL/version and malware policy; protected download/rendering, deletion/hold propagation, no permission widening. This does not authorize the 2nd Brain or a new index/embedding service |
| `syn-publishing` — disabled/unresolved | Future approved public artifact release; first candidate remains offline preview/checklist only | Irreversible disclosure, brand/legal error, platform impersonation, audience mismatch, hidden asset metadata, scheduler timing and duplicate releases | Only a selected brand account and draft/preview operation if vendor supports it; publish/schedule/admin rights excluded until separate release authority | Exact content/media digest, channel/audience/time/version, rights and independent legal/brand approval; human release gate, cancellation limits and correction/retraction plan. A delete cannot guarantee undo of publication |

## Direction and system ownership constraints

- Default direction is **none**. The matrix's “first candidate” is a design
  priority, not implemented transport or approved live data access.
- HubSpot commercial changes may produce an authenticated observation/intake
  proposal. They cannot directly accept a journey, change policy or complete work.
- Slack messages contain minimal approved projection references, not raw directives,
  approval evidence, tokens, protected payloads or a copy of the operating ledger.
- Model/document/knowledge material is untrusted input. Content instructions cannot
  override system policy, select tools, authorize recipients or expand tenant access.
- Each destination/account is bound server-side to the verified MC tenant; no
  browser or webhook selects that binding. Contacts are not authentication users.
- Never enable two connectors together to “test the loop.” Each action/direction
  has independent approval, receipts, stop criteria and rollback ownership.

## Evidence packet and safe activation sequence (future only)

For each proposed action retain: connector/account/tenant, purpose and field map,
classified samples (synthetic initially), exact candidate permissions, selected
vendor/version/terms, business/security reviewers, readiness-control evidence
revisions/digests/expiry, tests, cost/rate budget, audit/retention, kill-switch and
rollback proof, and CEO scope/time bounds. Secret values and raw records do not
belong in this packet or Git.

Future sequence after separate approval: offline contract → isolated synthetic
sandbox → independently witnessed least-privilege/recovery proof → separately
approved read-only bounded trial → separately approved mutation, if justified.
Do not jump from a successful mock directly to an enabled production connector.
When any evidence expires, a scope expands, an audience changes, a credential is
revoked or an outcome is unknown, fail closed and stop dispatch.

## Official-reference verification queue

These are reference starting points, **not fetched or live-validated in this
assessment**. Vendor owner must verify current product documentation and account
entitlements and record the version/date before C1 can pass:

- OpenAI developer documentation: <https://platform.openai.com/docs/>
- Slack API documentation: <https://api.slack.com/>
- HubSpot developer documentation: <https://developers.hubspot.com/docs/>
- Email/calendar/document/publishing vendor and the 2nd Brain platform: not selected.

No vendor account, credential, subscription, tenant configuration or endpoint was
queried. Product-specific guarantees remain explicit open decisions.
