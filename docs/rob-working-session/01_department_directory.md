# Enterprise Department Directory

> The six entries below are **configured routing contexts**, not evidence of staff, budgets, operating procedures, or fully functioning departments. Evidence: `mission_control/departments.json` (all department objects). Similar names have not been merged.

## Summary matrix

| Department / function | Inputs | Outputs | Reports To | Tools | Status | CEO escalation |
|---|---|---|---|---|---|---|
| Media & Editorial Division | Editorial/source directives | Templated governed recommendation | CEO in mock output; formal line **UNKNOWN** | CLI, provider, JSONL | **PARTIAL** | External publication/founder voice |
| Podcast Operations Division | Podcast/guest directives | Templated production recommendation | CEO in mock output; formal line **UNKNOWN** | Same | **PARTIAL** | Release/guest-sensitive decisions |
| Strategic Partnerships Division | Partnership/relationship directives | Templated relationship-first recommendation | **UNKNOWN** | Same | **PARTIAL** | Commitments, sponsorship, relationship risk |
| AI Innovation Division | AI/automation directives | Templated governed-AI recommendation | **UNKNOWN** | Same; optional OpenAI | **PARTIAL** | Privacy, representation, material automation risk |
| Publishing Division | Book/IP directives | Templated publication-path recommendation | **UNKNOWN** | Same | **PARTIAL** | Authorship, IP, publication commitment |
| CEO Command Center | Strategy/unmatched directives | Prioritized guidance template | CEO relationship **UNKNOWN** | Same; fallback router | **PARTIAL** | Cross-enterprise priority/conflict |
| CEO Desk | Requests executive synthesis | Proposed weekly/decision schema | CEO | No implementation | **CONCEPTUAL** | Decisions identified in proposed schema |

## Configured functions

### Media & Editorial Division

- **Mission/primary responsibilities:** transform source material into governed editorial intelligence and durable media assets; preserve founder voice, fact/interpretation boundaries, reuse, and Legacy Over Likes™.
- **Inputs/outputs:** article, journal, editorial, story, media, repurpose, or transcript directives → generic recommended execution and CEO closeout. Actual article production is possible only in live generative mode and was not validated.
- **Dependencies/recipients:** source material, audience, decision owner, deadline → CEO/human reviewer; cross-channel recipients **UNKNOWN**.
- **Owner / AI role:** configured “Chief Media Executive” (role label; human/AI nature **UNKNOWN**); mock or OpenAI specialist provider.
- **Systems/approvals/cadence:** Python CLI/provider/JSONL; human executive review before publication; cadence **UNKNOWN**.
- **Escalate:** factual conflict, founder-voice uncertainty, external publication, sensitive relationship or brand representation.
- **Status:** **PARTIAL**. **Evidence:** `departments.json` (`media_editorial`); `providers.py` (`execute`); README “Primary demonstration.”
- **Open:** Who owns editorial QA, facts, rights, and final approval?

### Podcast Operations Division

- **Mission/responsibilities:** prepare, produce, distribute, and preserve transformational podcast conversations; emphasize transformation, audience value, accurate production details, and release workflow.
- **Inputs/outputs:** podcast/episode/guest/interview/audio/video/show directive → generic recommendation; no tracker, media processing, scheduling, distribution, or preservation implementation.
- **Dependencies/recipients:** guest/source details and approvals; recipients **UNKNOWN**.
- **Owner / AI role:** configured “Chief Podcast Operations Executive”; AI specialist context.
- **Systems/approvals/cadence:** CLI/provider/JSONL; final release/human representation approval required by governance principle; cadence **UNKNOWN**.
- **Escalate:** guest sensitivity, release decision, accuracy dispute, missing assets/consent, public commitment.
- **Status:** **PARTIAL**. **Evidence:** `departments.json` (`podcast_operations`); README “Primary demonstration.”
- **Open:** Where are authoritative episode records, releases, consents, and owners?

### Strategic Partnerships Division

- **Mission/responsibilities:** relationship-first collaboration and durable mutual value; preserve trust and avoid transactional handling.
- **Inputs/outputs:** partner/collaboration/sponsor/relationship/outreach/follow-up directive → generic recommendation.
- **Dependencies/recipients:** relationship history and approved value proposition → CEO and counterpart-facing owner **UNKNOWN**.
- **Owner / AI role:** configured “Chief Partnerships Officer”; AI may prepare, not commit.
- **Systems/approvals/cadence:** CLI/provider/JSONL; CEO approval for sponsorship, commitments, sensitive outreach, compensation, and representation; cadence **UNKNOWN**.
- **Escalate:** promise, commercial/legal term, sensitive relationship, conflicting history.
- **Status:** **PARTIAL**. **Evidence:** `departments.json` (`strategic_partnerships`); mock human-authority statement in `providers.py`.
- **Open:** What promises exist, and where is relationship history authoritative?

### AI Innovation Division

- **Mission/responsibilities:** governed AI for automation, intelligence, education, and responsible innovation; disclose validation boundaries and protect private data.
- **Inputs/outputs:** AI/automation/workflow/technology directive → generic recommendation; optional live model output.
- **Dependencies/recipients:** approved use case, data classification, validation criteria → process owner/CEO **UNKNOWN**.
- **Owner / AI role:** configured “Chief AI Innovation Officer”; mock/OpenAI provider.
- **Systems/approvals/cadence:** Python, OpenAI SDK (optional); approval required for private data, external effect, or roadmap claim; cadence **UNKNOWN**.
- **Escalate:** privacy/security risk, irreversible automation, unverified capability claim.
- **Status:** **PARTIAL**; live mode **validation required**. **Evidence:** `departments.json` (`ai_innovation`); `providers.py` (`OpenAIProvider`); README “Capability status.”
- **Open:** Approved models, data policy, budget, evaluation, and vendor controls?

### Publishing Division

- **Mission/responsibilities:** develop books and IP into structured publishable legacy assets; preserve authorship, continuity, IP value, and practical path.
- **Inputs/outputs:** book/chapter/manuscript/publish/author/Kindle/audiobook directive → generic recommendation.
- **Dependencies/recipients:** manuscript, rights, editorial plan → author/CEO/publishing owner **UNKNOWN**.
- **Owner / AI role:** configured “Chief Publishing Executive”; specialist generation support.
- **Systems/approvals/cadence:** CLI/provider/JSONL; CEO/rights-holder approval before publication; cadence **UNKNOWN**.
- **Escalate:** authorship, rights, material factual issue, commercial/publication commitment.
- **Status:** **PARTIAL**. **Evidence:** `departments.json` (`publishing`).
- **Open:** Who owns rights, editorial review, and release authority?

### CEO Command Center

- **Mission/responsibilities:** convert cross-enterprise directives into prioritized decisions, accountable ownership, next actions, risks, and preserved knowledge.
- **Inputs/outputs:** strategy/executive/CEO/decision/priority/report/organization or unmatched directive → generic recommendation and CEO closeout.
- **Dependencies/recipients:** cross-enterprise context → CEO; no assignment/work queue exists.
- **Owner / AI role:** configured “Chief Strategy Officer”; mandatory fallback context.
- **Systems/approvals/cadence:** CLI/provider/JSONL; CEO final approval; cadence **UNKNOWN**.
- **Escalate:** priority conflict, missing owner, material risk, final governance authority.
- **Status:** **PARTIAL**. **Evidence:** `departments.json` (`executive_strategy`); `config.py` (required fallback); `providers.py` (fallback behavior).
- **Open:** Is this an AI role, human office, or both? How does it relate to CEO Desk?

### CEO Desk (requested executive function)

- **Mission/responsibilities:** consolidated decision/awareness interface and institutional-memory handoff.
- **Inputs/outputs:** department closeouts, risks, decisions, relationship attention → proposed CEO report schema in `03_ceo_desk_information_flow.md`.
- **Dependencies/recipients:** every operating function → CEO and archive.
- **Owner / AI role:** CEO is decision authority; AI preparation role **proposed, not approved**.
- **Systems/approvals/cadence:** none implemented; weekly cadence is **proposed** in this package.
- **Escalate:** decisions, blocked work, material risks, relationships, commitments.
- **Status:** **CONCEPTUAL / identity conflict unresolved**. **Evidence:** user-approved documentation scope; repository has only a shorter CEO summary template.
- **Open:** Approve name, relationship to CEO Command Center, owner, schema, cadence, and thresholds.
