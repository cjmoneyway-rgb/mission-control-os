# Founder-Dependency Register

> Repository evidence is too thin to prove that specific facts reside in CJ's inbox or memory. Items below are therefore either **evidenced decision dependencies** or **validation-required risks created by missing systems of record**. Recommendations do not remove CEO authority from sensitive decisions.

| Area | Dependency | Why CJ is currently required / evidence | Operational risk | Recommended artifact | Possible future owner | Automation | CEO approval | Priority |
|---|---|---|---|---|---|---|---|---|
| Relationship knowledge | Relationship history, trust boundaries, and appropriate outreach | No CRM/relationship dataset; partnership instructions prioritize trust (`departments.json`) | Context loss or damaging outreach | Relationship brief + contact/consent/provenance rules | Partnerships operations | Prepare reminders only; human-led contact | Yes | Critical |
| Guest status/history | Authoritative guest and episode history | Trackers/CRM absent; podcast context is only configuration | Duplicate outreach, missed promises, wrong status | Guest master record and status dictionary | Podcast coordinator | After cleanup, synchronize low-risk fields | Yes for sensitive exceptions | High |
| Episode release decisions | Final release and hold authority | Mock output states final approval remains with CEO (`providers.py`) | Premature or incorrect publication | Release approval record + hold checklist | Production lead prepares | No final approval automation | Yes | Critical |
| Editorial judgment | Founder voice, interpretation, and final public representation | Media instructions require founder-voice protection | Brand drift, factual/interpretive confusion | Voice guide, editorial rubric, fact log | Editor | Draft/QA aids only | Yes for external representation | Critical |
| Partnership promises | Existing promises, sponsorship, and collaboration terms | No commitments register; partnership context exists | Broken trust, unauthorized commitment | Commitments register with source and expiry | Partnerships lead | Alerts only | Yes | Critical |
| Scheduling | Priority overrides and sensitive rescheduling | No calendar/Calendly evidence or escalation rules | Conflicts and poor guest experience | Scheduling rules + exception matrix | Coordinator | Reminders after rules approved | For exceptions | Medium |
| Brand decisions | Use of trademarks, voice, and channel positioning | Brand phrases appear; no brand standard supplied | Inconsistent representation | Brand governance handbook | Editorial/brand lead | Lint/check assistance | Yes | High |
| Revenue/sponsorship | Pricing, inventory, terms, compensation | No revenue or sponsorship policy/data | Unauthorized commercial promises | Sponsorship policy + approval matrix | Revenue owner (TBD) | Reporting only initially | Yes | Critical |
| Department routing | Ambiguous/cross-department assignment | Current code chooses exactly one context; fallback is CEO Command Center | Lost handoffs and CEO bottleneck | Routing taxonomy + RACI + escalation SLA | Operations lead | Suggest route; human handles ambiguity | Yes for policy | High |
| Strategic priorities | Priority, capacity, and tradeoffs | No backlog, capacity data, or approved KPIs | Work selected without strategy/capacity | Quarterly priorities + weekly decision log | Chief of staff/operations | Rollups only | Yes | Critical |
| Exceptions/conflict | Conflicting sources, failed governance, disputes | Governance cannot resolve facts; one retry can still fail (`engine.py`) | Unsafe delivery or silent unresolved conflict | Exception register + stop-work rules | Governance owner | Detection/alerts only | Yes for material cases | High |
| Unwritten operations | Owners, SLAs, handoffs, definitions of done | Named operational source documents absent | Inconsistent execution; fragile scale | SOP library + operating glossary | Process owners | Document first | Yes to approve policy | High |

## Immediate capture order (recommendation — not approved)

1. Commitments and relationship context that could cause reputational or legal harm.
2. Release authority, active episode state, guest consent, and factual holds.
3. Strategic priorities, work owners, and escalation boundaries.
4. Editorial/brand decision rules and exception examples.
5. Operational SOPs, field definitions, and recurring cadence.
