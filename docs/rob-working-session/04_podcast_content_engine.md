# Podcast and Content Engine — Current-State Map

## Evidence boundary

The repository has a **PARTIAL planning/generation prototype**, not an end-to-end podcast engine. It can route podcast terms to Podcast Operations and article/journal terms to Media & Editorial, but it selects only one department and has no lifecycle state, CRM, calendar, storage, media production, publishing, social, or notification integration. The README describes potential outputs and a demonstration narrative; those are not proof of operational stages.

## Lifecycle map

Abbreviations: **H** human-led; **A0** no automation; **P** prototype can prepare generic text; **U** unknown due to missing source.

| Stage | Trigger / owner | Inputs → actions → outputs | Tool / status / timing | Approval / failure / escalation | Automation / evidence / gaps |
|---|---|---|---|---|---|
| Guest Discovery | Trigger/owner **U** | Leads → identify candidate → candidate record | **U** / no field / no SLA | Sensitive relationship → CEO | **A0**; no evidence; roster/criteria missing |
| Qualification | Candidate / owner **U** | Profile/context → assess fit → recommendation | **U** / no score / no SLA | Final guest approval human/CEO | **H**; guest-routing keywords only; rubric missing |
| CRM Entry | Approved/intake / owner **U** | Identity, provenance, consent → dedupe/store → CRM ID | HubSpot/Sheets **PLANNED/UNKNOWN** | Duplicate/consent conflict → data owner | **A0**; README says writeback roadmap; schema missing |
| Scheduling | Approval / owner **U** | Availability/time zone → coordinate → booking | Calendar/Calendly **UNKNOWN** | Exception or sensitive reschedule → human/CEO | **A0**; no integration/SLA |
| Asset Collection | Booking / owner **U** | Bio, headshot, links, releases → validate → asset-ready flag | Drive/email **UNKNOWN** | Missing rights/consent → hold | **A0**; checklist/storage missing |
| Research | Scheduled guest / owner **U** | Approved sources → research/fact log → research pack | Provider may draft **P** | Conflicts/unverified claims → human | **P/H**; no source citation or fact-validation mechanism |
| Executive Guest Brief | Research ready / owner **U** | Research + relationship context → synthesize → brief | Prototype text generation **P** | CEO approval for sensitive positioning | **P/H**; no defined brief schema |
| Recording | Scheduled session / owner **U** | Guest, run-of-show, consent → record → media files | StreamYard **UNKNOWN** | Consent/technical failure → production owner | **A0**; no recording integration |
| Post-Interview Intelligence | Recording/transcript / owner **U** | Transcript → insights/follow-ups → intelligence record | Media/podcast context **P** | Sensitive interpretation → CEO/human | **P/H**; README potential output; no verified transcript pipeline |
| Editing | Media ready / owner **U** | Raw media → edit → review cut | **U** / no status / no SLA | Missing media/rights → hold | **A0**; no media tooling |
| Quality Control | Edit ready / owner **U** | Cut/metadata/facts → QC → pass/issues | **U** | Factual/brand/technical failure → owner/CEO as material | **H**; code governance is text-heading/secret check only |
| Release Scheduling | QC pass / owner **U** | Approved cut/calendar → select date → release plan | **U** | Final release decision → CEO | **H**; no calendar or approval workflow |
| Publishing | Approved release / owner **U** | Media/metadata → publish → URLs | Hosting/YouTube **UNKNOWN** | Missing approval/rights/platform failure → stop | **H/A0**; no publisher integration |
| Journal Guest Edition | Transcript/intelligence / editorial owner **U** | Sources → draft/fact/edit → approved edition | Media context can recommend **P** | Founder voice/facts/publication → CEO/editor | **P/H**; sample directive, no production workflow |
| LinkedIn & Distribution | Approved assets / owner **U** | Edition/episode → channel copy → posts/links | LinkedIn/other channels **UNKNOWN** | Public representation → authorized human | **H/A0**; no integration |
| Guest Follow-Up | Publication/interview / owner **U** | Links/promises/context → personalized follow-up → interaction record | CRM/email **UNKNOWN** | Sensitive relationship/promises → CEO | **H**; partnership context only |
| Alumni Relationship | Follow-up complete / owner **U** | History/preferences → stewardship → next-touch plan | CRM **UNKNOWN** | Relationship nuance → human/CEO | **H**; no lifecycle or CRM evidence |
| Future Collaboration | Opportunity signal / owner **U** | Relationship + mutual value → qualify → proposal/decline | Partnerships context **P** | Commitments/sponsorship/compensation → CEO | **H/P**; no commitments register |

## Three-Episodes-Per-Week Repeatability Model

> **RECOMMENDATION / CAPACITY HYPOTHESIS — NOT APPROVED, IMPLEMENTED, OR PROVEN FEASIBLE.** “Three” comes from the requested planning scenario, not repository performance evidence.

### Proposed weekly cadence

Use three staggered production lanes rather than attempting each lifecycle in one week:

| Time | Release lane | Next-week lane | Later lane |
|---|---|---|---|
| Monday | Episode/Journal A final approval and scheduling | B edit + Journal draft | C research/assets |
| Tuesday | Publish/distribute A; record follow-up | B QC | C guest brief |
| Wednesday | Episode/Journal B final approval and scheduling | C edit + Journal draft | A-next research/assets |
| Thursday | Publish/distribute B; record follow-up | C QC | B-next guest brief |
| Friday | Episode/Journal C approval/publish; weekly reconciliation | Next releases readiness review | CEO exceptions/next-seven-days |

Exact release days, recording days, lead times, and batch sizes require CEO and production-owner approval.

### Capacity assumptions to validate

- Three fully consented, scheduled, recorded guests and usable recordings are ready ahead of release week.
- Named owners exist for coordination, research, editing, QC, editorial, publishing, CRM, and approvals; roles may overlap only after time study.
- Each episode and Journal edition has reserved editing/review capacity and a backup owner.
- CEO decision windows and hold rules are scheduled.
- One authoritative episode ID joins CRM, tracker, assets, approvals, and published URLs.
- Platform limits, contractor capacity, turnaround times, and correction rates are **UNKNOWN**.

### Required handoffs and bottlenecks

Required handoffs: qualified guest → CRM → booking/assets → research/brief → recording → transcript/intelligence → edit → QC/approval → release + Journal → distribution → follow-up/CRM/alumni.

Likely validation points—not proven current bottlenecks—are missing authoritative status, missing assets/consent, founder-only context/approval, editing and fact-check capacity, parallel episode/Journal coordination, and manual cross-system updates. Single points of failure are CJ for protected decisions and any unnamed sole production/editorial owner.

### Minimum viable dashboard fields (proposed)

Episode ID; guest/CRM ID; relationship sensitivity; referral provenance; lane/stage; accountable owner; next action/due date; recording/release dates; assets/consent/research/transcript/edit/QC/Journal readiness; approval status/approver/time; hold reason; episode/Journal/channel URLs; follow-up due/completed; data-quality flag; last updated/source.

### Recommended notifications

Low-risk reminders: upcoming due date, missing non-sensitive asset, stale status, approved release published, follow-up due. Alerts requiring human review: consent absent, conflicting facts, approval missing, schedule slip threatening release, sensitive relationship, public correction, failed publish, commitment/opportunity. Avoid automated external guest messages until templates, consent, sender authority, and exception handling are approved.

### CRM updates and CEO visibility

CRM should hold relationship identity, provenance, consent/preferences, interactions, and lifecycle; the podcast tracker should hold production state; both should link by stable ID. CEO Desk should receive decisions, material holds, relationship attention, risks, approved weekly KPI rollups, and seven-day approvals—not routine task chatter. Source-of-truth ownership remains a CEO/Rob decision.
