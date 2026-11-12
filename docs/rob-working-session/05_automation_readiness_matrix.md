# Automation Readiness Matrix

Categories: **A AUTOMATE NOW** (only bounded, reversible, internal actions); **B DOCUMENT FIRST**; **C CLEAN DATA FIRST**; **D KEEP HUMAN-LED**. “Suggested tool” is a recommendation, not an approved platform decision.

| Workflow | Current state | Data quality | Rule clarity | Risk | Category | Prerequisite | Human approval | Suggested tool | Evidence |
|---|---|---|---|---|---|---|---|---|---|
| Guest intake | No form/schema | Unknown | Low | Medium | **B** | Fields, consent, owner, dedupe rules | Exceptions | Approved form → CRM staging | Trackers/CRM missing |
| Guest scoring | No rubric | Unknown | Low | High/reputational | **D** | Document rubric; advisory only | Final approval always | Human review + optional worksheet | Podcast keywords only |
| Scheduling reminders | No integration | Unknown | Medium | Low if internal | **B** | Calendar source, timing, exceptions | Template/rules | Calendar automation TBD | No calendar evidence |
| Asset collection | No checklist/store | Unknown | Low | Medium/rights | **B** | Checklist, consent, storage, reminders | External templates | Workflow tool TBD | No asset pipeline |
| Research milestones | Generic generation only | Unknown | Low | Medium/factual | **B** | Brief schema, sources, fact checks | Brief release | Task system | Provider can generate, not validate |
| Episode status updates | No status model | Unknown | Low | Medium | **B** | Tracker/source-of-truth and definitions | Exception changes | Tracker automation TBD | No lifecycle state |
| Release notifications | No publisher/status source | Unknown | Low | High/public | **B** | Approved release event/templates | External notices | Hosting webhook/Zapier TBD | No integration |
| CRM updates | README roadmap | Unknown | Low | High/data | **C** | Dedupe, field ownership, consent, IDs | Sensitive records | HubSpot native/API TBD | README capability status |
| Referral-source preservation | No data supplied | Unknown | Medium concept | High/trust | **C** | Clean provenance and overwrite rules | Conflict resolution | CRM controlled field | Relationship instructions |
| Alumni follow-up | No lifecycle/history | Unknown | Low | High/relationship | **D** | Stewardship policy/context | Each sensitive outreach | Human-led CRM task | Partnerships context |
| Journal assignment | No queue/owner | N/A | Low | Medium | **B** | RACI, capacity, acceptance/SLA | Assignment exceptions | Task system | Media context only |
| LinkedIn content routing | No channel integration | Unknown | Low | High/public | **D** | Brand/channel policy | Every post until delegated | Draft queue only | No LinkedIn evidence |
| Weekly CEO reporting | Four-heading template only | Unknown | Medium proposal | Medium | **B** | Approve schema/sources/owners/KPIs | CEO accepts standard | Reporting layer TBD | `providers.py`; proposed schema |
| Department routing | Single keyword route | Config only | Medium | Medium/high | **B** | Taxonomy, multi-route/RACI, thresholds | Ambiguous/material route | Existing router as advisory | `providers.py` |
| Task reminders | Not implemented | N/A | High once tasks exist | Low/internal | **A** | Approved task source, owner, due date, quiet hours | Rules once; exceptions | Native task reminders | Reversible; no external representation |
| KPI rollups | No KPI data/definitions | Unknown | Low | Medium/misleading | **C** | Approved definitions, lineage, reconciliation | KPI definition/sign-off | BI/reporting TBD | No metrics implementation |
| Partnership alerts | No relationship/commitment data | Unknown | Low | High | **D** | Policy and context | Every action/commitment | Human review queue | Partnerships configuration only |
| Email intake classification | No Gmail integration | Unknown/sensitive | Low | High/privacy | **B** | Data policy, sender rules, retention, confidence gate | Sensitive routing | Gmail/API TBD | No email evidence |
| Audit logging | Local append exists | Full payload; no controls | High for append | Medium/high privacy | **A** only for sanitized metadata; otherwise **B** | Minimize/redact, retention, failure handling | Governance policy | Existing JSONL writer | `audit.py`, `models.py` |
| Final guest approval | Manual authority | Contextual | Judgment-based | High | **D** | Approval record | **Always** | Human workflow | Operating principles |
| Sponsorship/compensation/public commitments | No system/policy | Unknown | Judgment/legal | Critical | **D** | Policies/registers | **Always** | Human governance | No operational evidence |
| Factual conflict resolution | Narrow structural check only | Unknown | Judgment-based | High | **D** | Source hierarchy/fact log | **Always** for material conflict | Human review | `governance.py` limitations |

## Safest immediate automation boundary

The only credible **AUTOMATE NOW** candidates are internal, reversible reminders based on already approved task records and sanitized audit metadata capture. Even these require a named source, retention rule, failure visibility, and human exception path. No external communication or public action qualifies now.
